import base64
import json
import sys
from uuid import uuid4

import nacl.signing
import xxhash
from nacl.exceptions import BadSignatureError

class Transaction:
    def __init__(self, sender, destination = 0, value = 0, data={}, timestamp=None, nonce=None, id=None, source_pub_key=None):
        self.source = str(sender) #This is the id of the source node
        self.source_pub_key = str(source_pub_key) #Only needed to match to genesis block so
        self.sender = str(sender) #Not sure if this is needed, changes every time it is relayed?

        self.destination = str(destination) #The intended destination of the transaction, when it arrives here it is considered completed

        self.value = value #The integer value of the transaction, some kind of id?

        self.data = data #The payload of the transaction, the smart contract normally

        self.timestamp = timestamp
        self.nonce = nonce #Used to sort the transaction? could just do it by timestamp
        self.id = id #This is the id of the transaction

        self.signature_chain = []

        self.json = False #This tag is an easy way to check if the transaction is in the sendable json format

        self.completed = False #A transaction is considered completed if it has arrived at its destination node

        if not id:
            self.id = str(uuid4())


    def __str__(self):
        return f"id: {self.id}, Destination: {self.destination}, from: {self.sender}, value: {self.value}, sig_chain_len: {len(self.signature_chain)}, Completed: {self.completed}, json: {self.json}"

    def add_signature(self, private_key, public_key, id, relayer_id):
        """Appends the next element of the PoR signature chain, signature generated for each node the transaction is sent too
        Parameters:
            private_key (bytes): Private key of the sender
            public_key (bytes): Public key of the sender
            id (str): The id of the sender
            relayer_id: the id of the receiver
            """
        if len(self.signature_chain) == 0:
            genesis_sig = GenesisSignatureChainEntry(public_key, id, relayer_id, self.data)
            genesis_sig.set_genesis_signature(private_key)
            self.signature_chain.append(genesis_sig)
        else:
            next_signature = SignatureChainEntry(public_key,id,relayer_id)
            next_signature.add_signature(private_key, self.signature_chain[-1].signature)
            self.signature_chain.append(next_signature)


    def sig_chain_to_json(self):
        """This function serialises the public key and signature, it then converts the signature chain entry
         objects into json so they can be sent over the sockets #
         This is done because the nested object inside the transaction object cannot be sent, along with the
         cryptographic elements that need to be serialised."""
        json_chain = []
        #This doesnt change back? could explain the issues when verifying tbh, but just gonna leave it
        for sig in self.signature_chain:
            sig.sig_to_json()
            json_chain.append(json.dumps(sig.__dict__))
            sig.json_to_sig()
        self.signature_chain = json_chain
        self.json = True




    def json_to_sig_chain(self):
        sig_chain = []
        for index, sig in enumerate(self.signature_chain):
            data = json.loads(sig)
            if index == 0:
                instance = GenesisSignatureChainEntry(data['public_key'], data['id'], data['relayer_id'], self.data)
            else:
                instance = SignatureChainEntry(data['public_key'], data['id'], data['relayer_id'])
            instance.signature = data['signature']

            instance.json_to_sig()
            sig_chain.append(instance)

        self.signature_chain = sig_chain
        self.json = False




class SignatureChainEntry:
    """
    Contains the data for the elements in the signature chain
    Attributes
        id - The id of the sender
        public_key - The public key of the sender
        relayer_id - The id of who is going to recive the transaction
        signature_chain - The signature for this element in the chain
    """
    def __init__(self, public_key, id, relayer_id):
        self.id= id # Id of the source / sender
        self.public_key = public_key #public key of the sender / source, functionally the same
        self.relayer_id = relayer_id
        self.signature = None

    def add_signature(self, private_key, last_signature):
        data_arr = [last_signature, self.id, self.relayer_id]
        self.sign(private_key, data_arr)

    def sign(self, private_key, data_arr):
        """This function creates a signature using the private key
        Params
            private key: the private key used to sign
            data_arr : the contents of the signature
        """
        message = ""
        for data in data_arr:
            message += str(data) + ":"
        message = message[:-1]  # Takes the last colon off the message

        message_hash = xxhash.xxh64(message).digest()

        signed_message = private_key.sign(message_hash)

        self.signature = signed_message.signature

    def sig_to_json(self):
        self.public_key = pub_key_to_json(self.public_key)
        self.signature = signature_to_json(self.signature)

    def json_to_sig(self):
        self.public_key = json_to_pub_key(self.public_key)
        self.signature = json_to_signature(self.signature)

    def __str__(self):
        return f"id: {self.id}, relayer_id: {self.relayer_id}, public key: {self.public_key}, signature: {self.signature} "


class GenesisSignatureChainEntry(SignatureChainEntry):
    """
    Contains the data for the first element in the signature chain
    Attributes
        payload_hash - the hashed value of the payload
        payload_size - the size in bytes of the payload
        source_id - the id of the node that generated the transaction
        source_pub_key - the public key of the node that generated the transaction
        signature - genesis signature
    """
    def __init__(self, source_pub_key, source_id, relayer_id, payload):
        super().__init__(source_pub_key,source_id,relayer_id)
        self.payload_size = sys.getsizeof(payload)
         # Converting to string to be encoded into the hash, if comparing hashes, will needed to convert again
        self.payload_hash = xxhash.xxh64(str(payload).encode()).intdigest() #encode transforms string into bytes, indigest transforms the hash from bytes to ints

    def set_genesis_signature(self, private_key):
        #print(self.public_key,"Set genesis signature")
        data_arr = [self.payload_hash, self.payload_size, self.id, pub_key_to_json(self.public_key), self.relayer_id]
        self.sign(private_key, data_arr)


def validate_signature(sig, chain, index):
    if isinstance(sig, GenesisSignatureChainEntry):
        # Re-creating the message
        #print(f"Validate signature? {sig.public_key}")
        message = f"{sig.payload_hash}:{sig.payload_size}:{sig.id}:{pub_key_to_json(sig.public_key)}:{sig.relayer_id}"
        message_hash = xxhash.xxh64(message).digest()

    else:
        # [last_signature, self.id, self.relayer_id]
        last_sig = chain[index-1].signature
        message = f"{last_sig}:{sig.id}:{sig.relayer_id}"
        message_hash = xxhash.xxh64(message).digest()

    try:
        sig.public_key.verify(
            message_hash,
            sig.signature
        )
    except BadSignatureError as e:
        print(e, "Invalid Signature")
        return False
    return True

def validate_chain(chain):
    """This is a function that checks to see signature chain is valid
    A chain is only valid if the relayer ID matches the id of the next element in the chain
    All signatures have to be cryptographically valid"""

    for i in range(len(chain) - 1): #Needs to be minus 2?
        if chain[i].relayer_id != chain[i + 1].id:
            print("Invalid relayer id")
            return False

    for index, sig in enumerate(chain):
        if not validate_signature(sig, chain, index):
            print("Invalid signature validate chain")

            return False

    return True

def validate_transaction(transaction):
    #Validate the payload hash
    payload_hash = xxhash.xxh64(str(transaction.data)).intdigest()

    if payload_hash != transaction.signature_chain[0].payload_hash:
        print("Payload hash not verified")
        return False

    #Validate the payload size
    payload_size = sys.getsizeof(transaction.data)
    if payload_size != transaction.signature_chain[0].payload_size:
        print("Payload size not verified")
        return False

    #Validating the signature chain
    if not validate_chain(transaction.signature_chain):
        print("Transaction chain not valid")
        return False

    #Validate source id and key
    if str(transaction.source) != str(transaction.signature_chain[0].id):
        print("Transaction source not verified")
        return False

    if str(transaction.source_pub_key) != str(transaction.signature_chain[0].public_key):
        print("Transaction source public key not verified")
        return False

    return True

def signature_to_json(signature):
    return base64.b64encode(signature).decode("utf-8")

def json_to_signature(signature):
    return base64.b64decode(signature)

def json_to_pub_key(json_pub_key):
    # print(json_pub_key, "To pub key object")
    return nacl.signing.VerifyKey(base64.b64decode(json_pub_key))

def pub_key_to_json(pub_key):
    # print(pub_key,   "Convert to json")
    key_bytes = bytes(pub_key)
    return base64.b64encode(key_bytes).decode("utf-8")


