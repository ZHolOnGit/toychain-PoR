import json
import logging
from random import randint

from toychain.scs.deploy import Contract as State
from toychain.src.Transaction import signature_to_json, pub_key_to_json
from toychain.src.utils.helpers import compute_hash

logger = logging.getLogger('block')

class Block:
    """
    Class representing a block of a blockchain containing transactions
    """

    def __init__(self, height, parent_hash, data, miner_id, timestamp, nonce=None,
                 state_var=None, state = None):

        self.height = height
        self.number = height
        self.parent_hash = parent_hash
        self.data = data
        self.miner_id = miner_id
        self.timestamp = timestamp
        self.reception = 0


        if state:
            self.state = state
        else:
            self.state = State(state_var)

        self.nonce = nonce
        if nonce is None:
            self.nonce = randint(0, 1000)

        self.transactions_root = self.transactions_hash()
        self.hash = self.compute_block_hash()
        self.signature = None #Sign the block hash using the leader private key
        self.byzantine = False

    def sign_block(self, private_key):
        """This function digitally signs the block using the private key of the block creator"""
        signature = private_key.sign(self.hash.encode())
        self.signature = signature.signature

    def compute_block_hash(self):
        """
        computes the hash of the block header
        :return: hash of the block
        """
        _list = [self.height, self.parent_hash, self.transactions_hash(), self.miner_id, self.timestamp, self.nonce]

        self.hash = compute_hash(_list)

        return self.hash

    def transactions_hash(self):
        """
        computes the hash of the block transactions
        :return: the hash of the transaction list
        """
        transaction_list = []
        for t in self.data:
            t.sig_chain_to_json()
            transaction_list.append(t)
        self.transactions_root = compute_hash(transaction_list)
        for transaction in self.data:
            transaction.json_to_sig_chain()
        return self.transactions_root

    def get_header_hash(self):
        header = [self.parent_hash, self.transactions_hash(), self.timestamp, self.nonce]
        return compute_hash(header)

    def increase_nonce(self):  ###### POW
        self.nonce += 1

    def __str__(self):
        return f"height: {self.height}, minerId: {self.miner_id}, hash: {self.hash}, data: {self.data}, timestamp: {self.timestamp}"

    def __repr__(self):
        """
        Translate the block object in a string object
        """
        return f"## H: {self.height}, P: {self.miner_id}, BH: {self.hash[0:5]}, TS:{self.timestamp}, #T:{len(self.data)}, SH:{self.state.state_hash[0:5]}##"

    def to_json(self):
        return {
            "Height": self.height,
            "ParentHash": self.parent_hash,
            "Transactions": len(self.data), 
            "Miner": self.miner_id,
            "Timestamp": self.timestamp,
            "BlockHash": self.hash,
            "StateHash": self.state.state_hash if self.state else None,
            "Signature": signature_to_json(self.signature),
            "Frequency Estimate" : self.state.frequency_estimate,
            "Byzantine" : self.byzantine
        }

    #Edit this function to add +, what does this comment mean
    def to_json_string(self):
        return json.dumps(self.to_json(), indent=4)