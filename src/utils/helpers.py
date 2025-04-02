import base64
import struct
from hashlib import sha256

import nacl.bindings
import nacl.signing
import xxhash


def compute_hash(list):
    """
    Computes the hash of all the elements contained in the list by putting them in a string
    """
    if len(list) < 1:
        return
    hash_string = ""
    for elem in list:
        hash_string += str(elem)

    return xxhash.xxh64(hash_string.encode()).hexdigest()


def transaction_to_dict(transaction):
    return vars(transaction)

    # return {"source": transaction.source, "destination": transaction.destination, "data": transaction.data,
    #         "value": transaction.value, "timestamp": transaction.timestamp, "nonce": transaction.nonce,
    #         "id": transaction.id}

def transaction_to_id(transaction):
    return {"id": transaction.id,
            "completed": transaction.completed}

def vote_to_dict(id, vote):
    return {"id": id,
            "vote": vote}




def block_to_list(block):
    """
    Translates a block in a list
    """
    data = []
    for t in block.data:
        data.append(transaction_to_dict(t))
    return [block.height, block.parent_hash, data, block.miner_id, block.timestamp, block.nonce,
            block.state.state_variables, signature_to_json(block.signature), pub_key_to_json(block.leader_public_key)]


def create_block_from_list(_list):
    height = _list[0]
    parent_hash = _list[1]
    data = []
    for d in _list[2]:
        data.append(dict_to_transaction(d))
    miner_id = _list[3]
    timestamp = _list[4]
    nonce = _list[5]
    state_variables = _list[6]
    signature = json_to_signature(_list[7])
    pub_key = json_to_pub_key(_list[8])

    return height, parent_hash, data, miner_id, timestamp, nonce, state_variables, signature, pub_key


class CustomTimer:
    def __init__(self):
        self.time_counter = 0

    def time(self):
        return self.time_counter

    # def sleep(self, period):
    #     starting_time = self.time()

    #     while self.time_counter < starting_time + period:
    #         sleep(0.01)

    def increase_timer(self):
        self.time_counter += 1

    def step(self):
        self.time_counter += 1

    def reset_timer(self):
        self.time_counter = 0

def gen_enode(id, host = '127.0.0.1', port = 0):
    if port == 0:
        port = 1233 + id
    return f"enode://{id}@{host}:{port}"


def signature_to_json(signature):
    return base64.b64encode(signature).decode("utf-8")

def json_to_signature(signature):
    return base64.b64decode(signature)

def json_to_pub_key(json_pub_key):
    # print(json_pub_key, "To pub key object")
    return nacl.signing.VerifyKey(base64.b64decode(json_pub_key))

def pub_key_to_json(pub_key):# I really dont understand
    # print(pub_key,   "Convert to json")
    key_bytes = bytes(pub_key)
    return base64.b64encode(key_bytes).decode("utf-8")


#These 2 functions might be unnecessary
def write_uint32(value):
    return struct.pack("<I", value)

def serialise_var_bytes(data):

    if data is None:
        return b'\x00'

    length = len(data)
    if length < 253:
        return bytes([length]) + data #A one byte value
    elif length <= 0xFFFF:
        return b'\xfd' + struct.pack("<H", length) + data #a 2 byte value
    elif length <= 0xFFFFFFFF:
        return b'\xfe' + struct.pack("<I", length) + data #a 4 byte value
    else:
        return b'\xff' + struct.pack("<Q", length) + data # a 8 byte value
