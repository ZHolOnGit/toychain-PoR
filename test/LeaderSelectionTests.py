import math
import unittest

from toychain.src.Node import Node
from toychain.src.Transaction import Transaction
from toychain.src.consensus.ProofOfAuth import ProofOfAuthority


class TestLeaderSelection(unittest.TestCase):
    def setUp(self):
        self.Node1 = Node(1 ,"localhost" ,"1000", ProofOfAuthority())
        self.Node2 = Node(2 ,"localhost" ,"1000", ProofOfAuthority())
        self.Node3 = Node(3 ,"localhost" ,"1000", ProofOfAuthority())
        self.Node4 = Node(4 ,"localhost" ,"1000", ProofOfAuthority())
        self.tran1 = Transaction(self.Node1.id, data={"reading1" :400, "reading2" :500, "reading3" :600, "reading4" :700}, source_pub_key=self.Node1.public_key)
        self.tran2 = Transaction(self.Node2.id, data={"reading1" :400, "reading2" :500, "reading3" :600, "reading4" :700}, source_pub_key=self.Node2.public_key)
        self.tran3 = Transaction(self.Node3.id, data={"reading1" :400, "reading2" :500, "reading3" :600, "reading4" :700}, source_pub_key=self.Node3.public_key)

        self.transaction_list = [self.tran1, self.tran2, self.tran3]
        L = 3 #Number of transactions in the mempool
        e =  1/(10*L)

        self.threshold = -(math.log(e)) / L


    def testThreshold(self):
        print(self.threshold)
        #Transactions get passed around
        self.tran1.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        self.tran2.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node2.id, self.Node3.id)
        self.tran3.add_signature(self.Node3.private_key, self.Node3.public_key, self.Node3.id, self.Node1.id)

        self.tran1.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node2.id, self.Node3.id)
        self.tran2.add_signature(self.Node3.private_key, self.Node3.public_key, self.Node3.id, self.Node1.id)
        self.tran3.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)

        for transaction in self.transaction_list:
            #value of last signaturte
            print(transaction.signature_chain[-1].signature)
            print(int.from_bytes(transaction.signature_chain[-1].signature,byteorder='big'))








