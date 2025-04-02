#This test will generate 2 sets of keys and some transations to see if they are created properly and if the signatures can be verified
import copy
import unittest

from toychain.src.Node import Node
from toychain.src.Transaction import GenesisSignatureChainEntry, SignatureChainEntry, Transaction, validate_transaction
from toychain.src.consensus.ProofOfAuth import ProofOfAuthority




class TestTransactionSignature(unittest.TestCase):

    def setUp(self):
        #TODO: Eventually change this to the PoR, only for consistency
        self.Node1 = Node(1,"localhost","1000", ProofOfAuthority())
        self.Node2 = Node(2,"localhost","1000", ProofOfAuthority())
        self.Node3 = Node(3,"localhost","1000", ProofOfAuthority())
        self.Node4 = Node(4,"localhost","1000", ProofOfAuthority())
        self.tran = Transaction(self.Node1.id, data={"reading1":400, "reading2":500, "reading3":600, "reading4":700}, source_pub_key=self.Node1.public_key)


    def testValidLen1(self):
        """The transaction was generated in the setup step, this will generate the genesis signature and 'send'
         it to Node 2"""
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        self.assertTrue(validate_transaction(self.tran))

    def testValidLen2(self):
        """Tests that a transaction is valid with a sig chain length of 2"""
        #Sending from Node 1 -> Node 2
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        #Sending from Node2 - > node 3
        self.tran.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node2.id, self.Node3.id)
        self.assertTrue(validate_transaction(self.tran))


    def testValidLen3(self):
        """Tests that a transaction is valid with a sig chain length of 3"""
        #Sending from Node1 -> Node2
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        #Sending from Node2 -> Node3
        self.tran.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node2.id, self.Node3.id)
        #Sending from Node3 -> Node4
        self.tran.add_signature(self.Node3.private_key, self.Node3.public_key, self.Node3.id, self.Node4.id)
        self.assertTrue(validate_transaction(self.tran))


    def testInvalidSigLen1(self):
        """Tests that the transaction flags as invalid if the payload of the transaction is altered or corrupted"""
        #Byzantine node tampers with the data
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        self.tran.data = {"corrupted" : "message"}
        self.assertFalse(validate_transaction(self.tran))


    def testInvalidChainLen2(self):
        """Tests that the transaction flags as invalid if the chain of sender to relayer is not observed"""
        # Sending from Node 1 -> Node 2
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        # Sending from Node2 - > node 3
        self.tran.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node3.id, self.Node3.id)
        self.assertFalse(validate_transaction(self.tran))

    #Pretty confident this works, could set up a __eq__ method on the signauture object to check
    def test_json_conversion(self):
        self.tran.add_signature(self.Node1.private_key, self.Node1.public_key, self.Node1.id, self.Node2.id)
        # Sending from Node2 - > node 3
        self.tran.add_signature(self.Node2.private_key, self.Node2.public_key, self.Node3.id, self.Node3.id)
        sig_hold = self.tran.signature_chain
        print(self.tran.signature_chain[0])
        self.tran.sig_chain_to_json()
        print(self.tran)
        self.tran.json_to_sig_chain()
#Could have test checking to see if source ID and key are correct