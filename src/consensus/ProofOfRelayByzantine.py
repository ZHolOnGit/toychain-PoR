import copy
import logging
import os

from aenum import Enum

from toychain.src.Block import Block, State
from toychain.src.Transaction import SignatureChainEntry
from toychain.src.consensus.ProofOfRelay import ProofOfRelay, LowestLast
from toychain.src.utils.helpers import load_key_pair

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

class MiningStates(Enum):
    MINING   = 1
    LEADER = 9
    BLOCK   = 10

class States(Enum):
    IDLE   =   1
    TRANSACT = 9
    RANDOM   = 10


class ProofOfRelayByzantine(ProofOfRelay):
    def __init__(self,genesis=GENESIS_BLOCK):
        self.genesis = genesis
        self.block_generation = LowestLastByzantine




class LowestLastByzantine(LowestLast):
    def __init__(self, node):
        super().__init__(node)
        self.sig_chain_cache = (0, None)
        self.private_key, self.public_key = load_key_pair("/home/zak-22/arg/toychain-argos/toychain/src/utils/byzantine_keys")

    def calculate_lowest_signature(self,transaction):
        """A byzantine version of the lowest signature function, this handles the logic for the byzantine voting.
        A Byzantine node will vote for a fictional node 0, it will search for the highest signature from node 1,
        this ensures that all byzantine nodes will agree on the same false candidate, and it will not accidenly be#
        the correct candidate."""

        if self.sig_chain_cache[1] is None:
            forged_signature = SignatureChainEntry(self.public_key, "0", "2")
            forged_signature.add_signature(self.private_key, "LOREM")
            self.sig_chain_cache = (0, forged_signature)



        #This soloution didnt work, sometimes didnt recive a signature with 1

        # sig_chain = transaction.signature_chain
        # #All nodes that vote for 0, have to have 1s public key so that it can be added to the winning sig,
        # # and use that to verify who signed the block
        # #This is kinda redundant but im leaving it in
        # for sig in sig_chain:
        #     if sig.id == '1':
        #         #print(f"BYZANTINE GOT ONE {sig}")
        #         current_value = self.compute_sig_value(sig)
        #         if current_value > self.sig_chain_cache[0]:
        #             #Do this a fair bit, have function to copy transaction / signature
        #             sig.sig_to_json()
        #             sig_to_set = copy.deepcopy(sig)
        #             sig.json_to_sig()
        #             sig_to_set.json_to_sig()
        #             sig_to_set.id = '0'
        #             self.sig_chain_cache = (current_value, sig_to_set)


    def create_block(self):
        """A byzantine version of the block creation function, assuming that all the nodes have converged to a single
        candidate state in the voting stage, if the byzantines won the vote, the first byzantine node will
        create the block, adding a tag so that the block created can be identified as a byzantine one """
        print(f"Block create id:{self.node.id} can:{self.candidate_state}")
        #IF one of the byzantine nodes gets voted, this conditional wont let them make a block
        if (self.node.id == '1' and self.candidate_state == '0') or self.node.id == self.candidate_state:
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
                state = previous_state)  # There has been no state added yet, will be the aggregation

            #Using the forged private key, corresponding public key sent out in winning signature
            if self.candidate_state == '0':
                block.sign_block(self.private_key)
                block.byzantine = True
            else:
                block.sign_block(self.node.private_key)
            #THis applys all the smart contracts stored on the transactions
            for transaction in block.data:
                block.state.apply_transaction(transaction, block)


            # Update the blockchain and mempool
            self.node.chain.append(block)
            self.node.produced_block = block.to_json_string()
            self.node.previous_transactions_id.update([tx.id for tx in block.data])
            self.node.mempool.clear()

            print(f"Block produced by Node {self.node.id}: byzantine {block.byzantine}")
            logger.info(f"{repr(block)}")
            logger.info(f"{block.state.state_variables} \n")


    def update_post_vote(self):
        self.sig_chain_cache = (0, None)
        self.candidate_state = None










