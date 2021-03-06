import gym, os, sys, select
import numpy as np
from ddpg_agent.ddpg_agent import DDPGAgent
from tensorboard_evaluation import Evaluation

solved_score = 1000


def ensure_path(p):
    if not os.path.exists(p):
        os.mkdir(p)

def train_agent(n_steps: int=500000, render: bool=False, early_stop=True):
    tensorboard_path = os.path.join(".", "tensorboard_ant")
    ensure_path(tensorboard_path)
    train_dict_keys = ["score", "loss", "expl"]
    tensorboard = Evaluation(tensorboard_path, train_dict_keys)

    env = gym.make('Ant-v2')

    # create new naive agent
    agent = DDPGAgent.new_trainable_agent(
        state_space=env.observation_space,
        action_space = env.action_space,
        exploration_magnitude=2.,
        exploration_decay=0.99999,
        learning_rate_actor=0.0001,
        learning_rate_critic=0.0001,
        n_units = [256, 256, 128],
    )

    total_steps, ep = 0, 0

    while total_steps < n_steps:
        steps, score, done, lo_loss_sum, = 0, 0, False, 0
        state = np.expand_dims(env.reset(), axis=0)

        ep += 1

        while not done and steps < MAX_STEPS_PER_EP:
            steps += 1
            action = agent.act(state=state, explr_mode="gaussian")

            if render:
                env.render()

            next_state, reward, done, _ = env.step(np.squeeze(action, axis=0))
            next_state = np.expand_dims(next_state, axis=0)

            lo_loss, hi_loss = agent.train(state, action, reward, next_state, done)
            # this is the single loss if DDPG, or the lo_loss if hierarchical
            lo_loss_sum += (1 / steps) * (lo_loss - lo_loss_sum) # avoids need to divide by num steps at end

            score += reward
            state = next_state

            if os.name != 'nt':
                # check user keyboard commands
                while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    line = sys.stdin.readline().strip()
                    # 'r' will toggle the render flag
                    if line == 'r':
                        render = not render
                    # 'q' will save the models and and training
                    elif line == 'q':
                        agent.save_model(saved_models_dir)
                        return
                    # 'm' for more episodes
                    elif line == 'm':
                        n_steps += 50000
                    # 'l' for less episodes
                    elif line == 'l':
                        n_steps -= 50000
                    # 'i' will increase the exploration factor
                    elif line == 'i':
                        agent.modify_exploration_magnitude(0.1, mode='increment')
                    # 'd' will decrease the exploration factor
                    elif line == 'd':
                        agent.modify_exploration_magnitude(-0.1, mode='increment')
                    # 'z' will zero the exploration factor
                    elif line == 'z':
                        agent.modify_exploration_magnitude(0.0, mode='assign')
                    # an empty line means stdin has been closed
                    else:
                        print('unknown command')


        total_steps += steps

        print(f' Episode {ep:4d}. Steps: {steps:4d}, Score: {score:4f}, Loss: {lo_loss_sum:.3f},' 
            + f' Expl: {agent.explr_magnitude:6f}, '
            + f' Global step: {total_steps} of {n_steps} ({(total_steps*100/n_steps):.2f}%)'
            )
        tensorboard.write_episode_data(
            ep, 
            eval_dict={
                "score": score,
                "loss": lo_loss_sum,
                "expl": agent.explr_magnitude,
                })
        
        if ep % 100 == 0:
            agent.save_model(saved_models_dir)
    
        #Early stop test
        if early_stop and score > 0.8 * solved_score:
            print(f'\n\n The agent reached a score of {score} while training. It is now eligible for an early stop test.')
            print('Initiating tests...')
            agent.save_model(saved_models_dir)
            if isSolved(min_score=solved_score):
                return

    agent.save_model(saved_models_dir)

def test_agent(n_episodes: int=10, render: bool=True):
    env = gym.make('Ant-v2')

    agent = DDPGAgent.load_pretrained_agent(
        filepath=saved_models_dir,
        state_space=env.observation_space,
        action_space = env.action_space,
    )
    
    all_scores = []
    for ep in range(n_episodes):
        done, steps, score = False, 0, 0
        state = np.expand_dims(env.reset(), axis=0)
        while not done:
            
            action = agent.act(state=state, explr_mode="no_exploration")

            if render:
                env.render()

            state, reward, done, _ = env.step(np.squeeze(action, axis=0))
            state = np.expand_dims(state, axis=0)

            score += reward
            steps += 1
        
        all_scores.append(score)
        print(f'Episode {ep} of {n_episodes}. score: {score}, steps: {steps}')
    return all_scores

def isSolved(n_episodes=100, min_score=1800):
    all_scores = test_agent(n_episodes=n_episodes, render=False)
    average_score = np.mean(all_scores)
    solved = average_score >= min_score
    neg = 'not ' if not solved else ' '
    print (f'\nProblem{neg}solved.')
    print (f'Mean score over {n_episodes} episodes: {average_score}')
    return solved


if __name__ == "__main__":
    MAX_STEPS_PER_EP = 1000
    saved_models_dir = os.path.join('.','ant_models')
    train_agent(n_steps=1000000)
    test_agent()
