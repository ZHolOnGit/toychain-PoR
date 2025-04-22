import copy
import logging
import urllib.parse


from toychain.src.utils.constants import MEMPOOL_SYNC_TAG, CHAIN_SYNC_TAG, BLOCK_REQUEST_TAG, MISSING_MEMPOOL_TAG, \
    GET_VOTE_TAG
from toychain.src.utils.helpers import transaction_to_dict, block_to_list, \
    transaction_to_id, vote_to_dict, dict_to_transaction

logger = logging.getLogger('w3')

class MessageHandler:

    def __init__(self, node_server):

        self.node_server = node_server
        self.node = node_server.node
        self.enode = self.node.enode

        # Message type to handler  mappings
        #TODO: Will need more of these for the voting stages
        self.requests_handler_mapping = {
            MEMPOOL_SYNC_TAG: self.handle_request_mempool,
            CHAIN_SYNC_TAG: self.handle_request_sync,
            BLOCK_REQUEST_TAG: self.handle_request_block,
            MISSING_MEMPOOL_TAG: self.handle_request_missing_mempool, #Missing mempool is the one that actually sends the missing transactions
            GET_VOTE_TAG: self.handle_vote_request
            }

        self.answers_handler_mapping = {
            MEMPOOL_SYNC_TAG: self.handle_answer_mempool,
            CHAIN_SYNC_TAG: self.handle_answer_sync,
            BLOCK_REQUEST_TAG: self.handle_answer_block,
            MISSING_MEMPOOL_TAG: self.handle_answer_missing,
            GET_VOTE_TAG: self.handle_vote_answer
            }

    def handle_request(self, msg):
        """
        Returns a message containing the requested information
        """
        if not self.validate_message(msg):
            return

        handler = self.requests_handler_mapping.get(msg["type"])
        content = handler(msg)
        return self.construct_message(content, msg["type"])

    def handle_answer(self, msg):
        """
        Processes the answer based on its type.
        """
        if not self.validate_message(msg):
            return

        handler = self.answers_handler_mapping.get(msg["type"])
        handler(msg)

    def construct_message(self, data, msg_type, receiver=None):
        return {
                "type": msg_type,
                "receiver": receiver,
                "sender": self.enode,
                "data": data
                }

    def validate_message(self, msg):
        mandatory_keys = {"data", "type", "receiver", "sender"}
        if not isinstance(msg, dict):
            logger.error(f"Invalid message format: {msg}")
            return False

        missing_keys = mandatory_keys - msg.keys()
        if missing_keys:
            logger.error(f"Message missing keys {missing_keys}: {msg}")
            return False

        return True

    ################# REQUEST HANDLERS ########################


    def handle_request_mempool(self, msg):
        """ Returns the current mempool as a list of ids """
        return [transaction_to_id(t) for t in self.node.mempool.values()]

    def handle_request_sync(self, msg):
        """ Returns the latest hash and difficulty """
        return self.node.get_block('last').get_header_hash(), len(self.node.chain)

    def handle_request_block(self, msg):
        """ Checks if one of the indicated blocks is in its chain
            Once a common block is found """
        #Might have to alter this one, but don't really see the harm in keeping the partial chain stuff
        #Assuming that there are no forks in the chain,
        #print(f"Block sync request data {msg['data']}, id that crashes {self.node.id}, id sender {msg['sender']}")
        for header_hash, height in msg["data"]:
            potential_common_block = self.node.get_block(height)
            if potential_common_block is None:
                return None, None

            if header_hash == potential_common_block.get_header_hash():
                # Common block found
                partial_chain = []
                i = height + 1
                while i < self.node.current_height:
                    partial_chain.append(block_to_list(self.node.get_block(i)))
                    i += 1
                return height, partial_chain
        return height, None

    def handle_request_missing_mempool(self, msg):
        """This function gets all the transactions that are requested by id, signs them, then sends them to the
        requester """
        transactions = []
        for dict in msg["data"]:
            transaction = self.node.mempool[dict["id"]] #TODO: Some issues with the completed transactions
            if transaction.completed: #TODO: Question, should a completed transaction remain in json form?
                transaction.sig_chain_to_json()
                transaction_to_send = copy.deepcopy(transaction)
                transactions.append(transaction_to_dict(transaction_to_send))
                transaction.json_to_sig_chain()
            else:
                #his is a bit of a mess and hopefully not too inefficient, but needs to be json to copy and send but needs
                #to have the actual signature stuff to sign
                transaction.sig_chain_to_json()
                transaction_to_send = copy.deepcopy(transaction)
                transaction_to_send.json_to_sig_chain()
                #self.node.get_block('last') - for getting the last block in the chain
                transaction_to_send.add_signature(self.node.private_key,self.node.public_key, self.node.id, urllib.parse.urlparse((msg["sender"])).username)
                #print(f"transaction {transaction_to_send} self {self.node.id}, transaction Nonce ,{self.node.my_transaction_nonce}, sending to {msg['sender']}, ")
                transaction_to_send.sig_chain_to_json()
                transactions.append(transaction_to_dict(transaction_to_send))
                transaction.json_to_sig_chain()


        #print(f"{len(transactions)} missing transactions sent")
        return transactions


    def handle_vote_request(self,msg):
        #print(f"get Vote id: {self.node.id} candidate: {self.node.mining_thread.candidate_state}")
        return vote_to_dict(self.node.id, self.node.mining_thread.candidate_state, self.node.mining_thread.sig_chain_cache[1])


    ################# ANSWER HANDLERS  ########################

    def handle_answer_mempool(self, msg):
       """This function takes the list of transactions given, finds the ones that it does not already have,
       and returns the id of these transactions back to the requester node"""
       missing_transactions = self.node.find_missing_transactions(msg["data"])

       if len(missing_transactions) > 0:
           self.request_transactions(missing_transactions, msg["sender"])

        # transaction_list = [dict_to_transaction(d) for d in msg["data"]]
        # self.node.sync_mempool(transaction_list)

    def request_transactions(self,missing_transactions, enode):
        """This function constructs, then sends the request containing the ids of the transactions that are
        missing from this node and need to be signed and sent from the sender"""
        request = self.construct_message(missing_transactions, MISSING_MEMPOOL_TAG,enode)
        self.node_server.send_request(enode,request)

    def handle_answer_sync(self, msg):

        peer_hash, peer_height   = msg["data"]
        local_hash, local_height = self.node.get_sync_info()

        #print(f"ID {self.node.id}, sender: {msg['sender']}, Answer sync LH:{local_height}, PH: {peer_height}, LHash: {local_hash}, PHash: {peer_hash}")

        # Case 1: My chain is already synchronized with the peer
        if local_hash == peer_hash:
            return
        #My chain is longer or equal length - equal len kinda checked above
        elif local_height >= peer_height:
            return
        # Case 3: Peer has longer chain
        else:
            self.request_block(self.node.current_height, msg["sender"])


    def handle_answer_block(self, msg):
        height, partial_chain = msg["data"]
        if height is None:
            return

        if partial_chain is None:
            self.request_block(height, msg["sender"])

        elif len(partial_chain) > 0:
            self.node.sync_chain(partial_chain, height)

    def request_block(self, current_height, enode):
        """ Send the last 5 blocks header hash """
        #TODO: Alter this so that it just sends the last block?

        content = []
        # Sends the block header + height of the last 5 blocks before the specified height
        for block in reversed(self.node.chain[max(0, current_height - 5):current_height]):
            content.append((block.get_header_hash(), block.height))

        request = self.construct_message(content, BLOCK_REQUEST_TAG, enode)
        self.node_server.send_request(enode, request)


    def handle_answer_missing(self,msg):
        """This function receives the requested transactions and adds them to the current mempool"""
        transaction_list = [dict_to_transaction(d) for d in msg["data"]]
        for transaction in transaction_list:
            transaction.json_to_sig_chain()
        self.node.sync_mempool(transaction_list)

    def handle_vote_answer(self,msg):
        """This function adds the vote received to the current collection of votes"""
        self.node.mining_thread.add_vote(msg["data"])




# OLD VERSIONS

    # def handle_answer_sync(self, msg):
    #     last_block = self.node.get_block('last')
    #     if msg["data"] == (last_block.get_header_hash(), last_block.total_difficulty):
    #         # Chains are synchronised
    #         if constants.DEBUG:
    #             logger.debug(f"Node {self.node.id} is chain sync")
    #         return

    #     if last_block.total_difficulty <= msg["data"][1]:
    #         # If the chains have equal sizes, node keeps his
    #         # If the chain of the node is longer than the received one, let him do the work
    #         self.request_block(len(self.node.chain), msg["sender"])
    #     else:
    #         if constants.DEBUG:
    #             logger.debug(f"Node {self.node.id} has a current diff of {last_block.total_difficulty}")
