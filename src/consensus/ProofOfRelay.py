import copy
import json
import logging
import os

from aenum import Enum
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from toychain.src.Block import Block, State
from toychain.src.Transaction import json_to_pub_key, SignatureChainEntry
from toychain.src.utils.constants import BLOCK_PERIOD

logger = logging.getLogger('por')

num_robots = int(os.environ['NUMROBOTS'])
try:
    num_neighbours = num_robots // 3
    if num_neighbours % 2 == 0:
        num_neighbours += 1
    if num_neighbours <= 1:
        num_neighbours = 3
    print(f"num neighbours: {num_neighbours}")
except ValueError:
    num_neighbours = 3

max_recent_leaders = 7 #Arbritray value

GENESIS_BLOCK = Block(0, 0000, [],  0, 0, nonce = 1, state = State(num_robots=num_robots))

#TODO: Have the different lengths of time for transaction propagation and leader / new block propagation?

# There are X states - The code (Well AI explaning the code) and the wiki seem to be saying different things
# Mining - The node receives transactions, adds them to the cache when appropriate
# Waiting for candidates - After a set ammount of time, each node transmits its chosen candidate,


class MiningStates(Enum):
    MINING   = 1
    LEADER = 9
    BLOCK   = 10

class States(Enum):
    IDLE   =   1
    TRANSACT = 9
    RANDOM   = 10


class ProofOfRelay:
    def __init__(self,genesis=GENESIS_BLOCK):
        self.genesis = genesis
        self.block_generation = LowestLast

    def verify_chain(self, chain, winning_signatures):
        """Function to check if the proposed new partial chain is valid considering the current state of the nodes blockchain"""
        last_block = chain[0] # The first element of the partial chain
        #print(f"winning sigs {winning_signatures}, height {last_block.height}")
        last_pubkey = winning_signatures[last_block.height-1].public_key


        if not self.verify_block(last_block, last_pubkey):
            return
        i=1
        while 1 < len(chain):
            last_block_hash = last_block.compute_block_hash()
            if chain[i].timestamp - last_block.timestamp < BLOCK_PERIOD: #TODO: this around 300?
                logger.error("Timestamp error in the blockchain")
                logger.error(len(chain))
                logger.error(f"Previous: {last_block.timestamp}, Current: {chain[i].timestamp}")
                logger.error(chain)
                return False

            elif not self.verify_block(chain[i], winning_signatures[chain[i].height-1].public_key):
                logger.error("Block error")
                logger.error(chain[i].__repr__())
                return False

            elif chain[i].parent_hash != last_block_hash:
                logger.error("Error in the blockchain")
                logger.error(chain[i].parent_hash + "###" + last_block_hash)
                return False
            else:
                last_block = chain[i]
            i += 1

        return True



    #Will need to figure out what to do if block is invalid, try and recive another? Go back to leader selection? to mining?
    def verify_block(self, block, public_key):
        """This function verifies that the newly received block is formed correctly and from the elected leader
        With the last_signature being the signature entry object of the elected leader
        """

        #TODO: this seems like a bit of cheat but sue me
        if type(public_key) != VerifyKey:
            public_key = json_to_pub_key(public_key)

        #Verify the block was signed / constructed by the elected leader, this public key should come from somewhere
        public_key.verify(
            block.hash.encode(),
            block.signature,
        )
        try:
            pass
        except BadSignatureError:
            return False
        #TODO: decide if any more block verification needs to be done

        print("BLOCK VERIFIED ")
        return True


#Similar to proof of authority, start leader selection, block selection ect at a set time
class LowestLast:
    def __init__(self, node):
        self.node = node
        self.sig_chain_cache = (float('inf') ,None) #a tuple of the lowest signature value and the sig chain entry associated with it
        self.checked_ids = [] #Contains the ids of the completed transactions that have had their signatures checked
        self.flag = False
        self.state = MiningStates.MINING
        self.candidate_state = None #Will be the id/enode of the candidate that is voting/voting for leader
        self.recent_leaders = [] # A list of the previous miners, used for applying penalties, store the signatures, can get the required keys
        self.all_complete = None
        self.vote_cache = [] # The cache of the votes received for this round of voting
        self.winning_signatures = [] #A list of the winning sig chain entry for each block - Hope there are no forks


    def run(self):
        """Perform the different stages of the block generation cycle """

        if self.state == MiningStates.MINING:
            for transaction in self.node.mempool.values():
                if transaction.completed and transaction.id not in self.checked_ids:
                    self.checked_ids.append(transaction.id)
                    self.calculate_lowest_signature(transaction)
            #len of the chain or the height of the last block, same difference really
            if (self.node.custom_timer.time() % (3 * BLOCK_PERIOD)) > BLOCK_PERIOD:
                self.state = MiningStates.LEADER
                self.node.mempool_sync_thread.stop()
                self.candidate_state = self.sig_chain_cache[1].id
                self.node.vote_sync_thread.start()
                print(f"Lowest mined signature: {self.sig_chain_cache[0]}, id: {self.sig_chain_cache[1].id} ")


        elif self.state == MiningStates.LEADER:
            #When all the votes are collected
            if len(self.vote_cache) == num_neighbours:
                candidate, count, winner_signature = self.count_votes()
                #If the majority votes for a certain candidate
                if count > (num_neighbours // 2):
                    self.candidate_state = candidate
                    self.sig_chain_cache = (candidate, winner_signature)

                self.vote_cache = []
            #After 100 ticks, the phase changes
            if (self.node.custom_timer.time() % (3 * BLOCK_PERIOD)) > (2* BLOCK_PERIOD): #TODO: These timings could do with shortening?
                self.state = MiningStates.BLOCK
                self.create_block()
                self.add_recent_leader(self.candidate_state)
                self.winning_signatures.append(self.sig_chain_cache[1])
                self.node.vote_sync_thread.stop()
                self.node.chain_sync_thread.start()

        elif self.state == MiningStates.BLOCK:
            self.update_post_vote()
            #The only thing in this block is to wait for the transactions to propogate
            #TODO: Try and understand what the apply transaction shit is, equivalent will be aggregating the new ground sent in?
            if (self.node.custom_timer.time() % (3 * BLOCK_PERIOD)) < BLOCK_PERIOD:
                print(f"END BLOCK PERIOD, chainP{self.node.chain}")
                self.state = MiningStates.MINING
                self.node.chain_sync_thread.stop()
                self.node.mempool_sync_thread.start()

    def create_block(self):
        print(f"Block create id:{self.node.id} can:{self.candidate_state}")
        if self.node.id == self.candidate_state:
            previous_block = copy.deepcopy(self.node.get_block('last'))
            previous_state = previous_block.state
            mempool = list((self.node.mempool.copy().values()))

            # Filter out transactions already on the blockchain
            data = [tx for tx in mempool if tx.id not in self.node.previous_transactions_id]
            # Generate the new block
            block = Block(
                previous_block.height + 1,
                previous_block.hash,
                data,
                self.node.id,
                # THis is the miner_id, it is the enode in other implementations but this makes more sense
                self.node.custom_timer.time(),
                state =previous_state)  # There has been no state added yet, will be the aggregation
            block.sign_block(self.node.private_key)

            #TODO: apply the transactions
            for transaction in block.data:
                block.state.apply_transaction(transaction, block)


            # Update the blockchain and mempool
            self.node.chain.append(block)
            self.node.produced_block = block.to_json_string()
            self.node.previous_transactions_id.update([tx.id for tx in block.data])
            self.node.mempool.clear()

            print(f"Block produced by Node {self.node.id}: ")
            logger.info(f"{repr(block)}")
            logger.info(f"{block.state.state_variables} \n")

    #These 2 functions are for testing
    def check_completed(self):
        for transaction in self.node.mempool.values():
            if not transaction.completed:
                return False
        return True

    def timing_check(self):
        #Timing checks for transaction propgation
        if self.check_completed():
            if len(self.node.mempool.values()) == num_robots and self.all_complete is None:
                self.all_complete = self.node.custom_timer.time()
                for tr in self.node.mempool.values():
                    print(f"transaction: {tr}, node {self.node.id} ")
                print(self.node.custom_timer.time(), self.node.id, len(self.node.mempool.keys()), "stamp")
        if self.node.custom_timer.time() == 200:
            print(f"id {self.node.id} completed in {self.all_complete}----------------------------------")
            for transaction in self.node.mempool.values():
                print(transaction)

    def step(self):
        if self.flag:
            self.run()

    def start(self):
        self.flag = True

    def stop(self):
        self.flag = False

    def calculate_lowest_signature(self,transaction):
        """A simplified variation of the NKN selection process, instead of calculating the sighash which involves
        setting up vfrs and complex cryptographic operations, this simply finds the signature with the lowest value, also instead of keeping a min heap of potential sig chains, since there is no reason
         why a node would be unreachable / unavailable to be leader, it will just be one spot instead of a cache"""

        # assumed that the chain was validated and completed when it was accepted by the node and passed in here
        sig_chain = transaction.signature_chain


        #print(f"sig chain len {len(sig_chain)}")
        for sig in sig_chain:
            current_value = self.compute_sig_value(sig)
            if current_value < self.sig_chain_cache[0]:
                self.sig_chain_cache = (current_value, sig)

    def get_recent_count(self, id):
        """This function returns the number of times the considered node appears in the recent leader list"""
        count = 0
        for sig in self.recent_leaders:
            if sig == id:
                count += 1
        return count

    def compute_sig_value(self, signature):
        """This function computes the numerical value """
        int_sig = int.from_bytes(signature.signature,byteorder="big")
        count = self.get_recent_count(signature.id)
        return int_sig << count

    def add_vote(self, vote_dict):
        self.vote_cache.append(vote_dict)

    def count_votes(self):
        """This function returns the id of the node with the most votes and the number of votes that it received"""
        frequency = {}
        for dict in self.vote_cache:
            if dict["vote"] in frequency.keys():
                frequency[dict["vote"]] += 1
            else:
                frequency[dict["vote"]] = 1

        id, count =  max(frequency.items(), key=lambda x: x[1])

        return id, count, self.get_voted_signature(id)


    def get_voted_signature(self, vote_id):
        """This function gets the json representation of the winning signature sent in during the voting stage
        and re creates it into a signature object """
        sig_dict = {}
        for dict in self.vote_cache:
            if dict["vote"] == vote_id:
                sig_dict = json.loads(dict["winning_sig"])

                break

        sig = SignatureChainEntry(sig_dict['public_key'], sig_dict['id'], sig_dict['relayer_id'])
        sig.signature = sig_dict["signature"]
        sig.json_to_sig()
        return sig


    def add_recent_leader(self, id):
        if len(self.recent_leaders) == max_recent_leaders:
            del self.recent_leaders[0]
        self.recent_leaders.append(id)

    def update_post_vote(self):
        self.sig_chain_cache = (float('inf'), None)
        self.candidate_state = None