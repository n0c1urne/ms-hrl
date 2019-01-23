from typing import List
from collections import namedtuple, deque
import numpy as np

ReplayBatch = namedtuple('ReplayBatch', ['states_before', 'actions', 'states_after','rewards','done_flags'])

class ReplayBuffer():
    def __init__(self, buffer_size: int=10000, batch_size: int=100):
        """
        Buffer will keep the most recent 'buffer_size' transitions
        Batches given by the function 'sample_batch()' will have length 'batch_size'
        """
        self.batch_size = batch_size
        self.states_before = deque(maxlen=buffer_size)
        self.actions = deque(maxlen=buffer_size)
        self.states_after = deque(maxlen=buffer_size)
        self.rewards = deque(maxlen=buffer_size)
        self.done_flags = deque(maxlen=buffer_size)

    def add(self, state_before: List[float], action: int, state_after: List[float], reward: float, done_flag: bool):
        """
        Add a new transition to the buffer
        """
        self.states_before.append(state_before)
        self.actions.append(action)
        self.states_after.append(state_after)
        self.rewards.append(reward)
        self.done_flags.append(done_flag)

    def len(self):
        """
        Returns how many transitions are currently stored in the buffer
        """
        return len(self.done_flags)

    def sample_batch(self) -> ReplayBatch:
        """
        Returns a batch of transtions sampled from the buffer
        """
        # The size of the batch shouldn't be larger than the number of transitions currently stored in the buffer
        b_size = self.batch_size if self.len() > self.batch_size else self.len()
        # Samples are chosen without replacement
        pick = np.random.choice(self.len(), size=b_size, replace=False)
        sb = np.array(self.states_before)[pick]
        ac = np.array(self.actions)[pick]
        sa = np.array(self.states_after)[pick]
        rw = np.array(self.rewards)[pick]
        df = np.array(self.done_flags)[pick]
        # Batch is stored in the namedtupple 'ReplayBatch'
        return ReplayBatch(states_before=sb, actions=ac, states_after=sa, rewards=rw, done_flags=df)





