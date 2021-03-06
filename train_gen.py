import select, sys, gym, os
import numpy as np
import argparse

from continuous_cartpole import ContinuousCartPoleEnv
from bipedal_walker import BipedalWalker

from ddpg_agent.ddpg_agent import DDPGAgent
from ddpg_agent.dummy_agent import DummyAgent
from teacher_agent.teacher_agent import TeacherAgent
from meta_agent import MetaAgent
from tensorboard_evaluation import Evaluation

# for CCP and bipedal respectively
# calculated from inspection / sampling
HI_ACTION_LIMITS = [[0.4, 0.6, np.pi / 4, 3],
                    [
                        1.93463567, 0.184130755, 0.350053925, 0.32318072,
                        1.025671095, 1.182890775, 1.236717375, 1.17722261, 0.5,
                        0.78032851, 1.1053074, 1.21445441, 1.66797805, 0.5,
                        0.203757265, 0.20607123, 0.21328325, 0.226284575,
                        0.2468781, 0.27847528, 0.327789575, 0.40950387,
                        0.388096935, 0.314850675
                    ]]


def ensure_path(p):
    if not os.path.exists(p):
        os.mkdir(p)


def test_agent(n_episodes: int = 10, render: bool = True):
    env = ContinuousCartPoleEnv() if not COMPLEXENV else BipedalWalker()
    env.seed(np.random.randint(9999))
    # load agent
    if not HIERARCHY:
        agent = DDPGAgent.load_pretrained_agent(
            filepath=saved_models_dir,
            state_space=env.observation_space,
            action_space=env.action_space)
    else:
        hi_action_space = gym.spaces.Box(
            low=np.negative(np.array(HI_ACTION_LIMITS[COMPLEXENV])),
            high=np.array(HI_ACTION_LIMITS[COMPLEXENV]),
            dtype=env.observation_space.dtype)

        agent = MetaAgent(
            models_dir=saved_models_dir,
            state_space=env.observation_space,
            action_space=env.action_space,
            hi_agent_cls=DummyAgent,
            lo_agent_cls=DDPGAgent,
            hi_action_space=hi_action_space,
        )

    all_scores = []
    for ep in range(n_episodes):
        score, steps, done = 0, 0, False
        state = env.reset()

        goal_state = np.squeeze(state)

        if HIERARCHY:
            agent.reset_clock()

        for steps in range(MAX_STEPS_PER_EP):
            action = agent.act(state)

            if render:
                if not HIERARCHY:
                    env.render()
                else:
                    env.render(goal_state=goal_state)

            if HIERARCHY:
                goal_state = np.squeeze(state + agent.goal)

            scaled_action = agent.scale_action(action)
            next_state, reward, done, _ = env.step(
                np.squeeze(scaled_action, axis=0))

            if HIERARCHY:
                agent.goal = agent.goal_transition(agent.goal, state,
                                                   next_state)

            state = next_state
            steps += 1
            score += reward
            if done:
                break

        all_scores.append(score)
        print(f'Episode {ep} of {n_episodes}. score: {score}, steps: {steps}')

    return np.array(all_scores)


def isSolved(n_episodes=100, min_score=1800):
    all_scores = test_agent(n_episodes=n_episodes, render=False)
    average_score = np.mean(all_scores)
    results = all_scores > min_score
    solved = np.all(results)
    failures = n_episodes - np.sum(results)
    neg = 'not ' if not solved else ' '
    print(f'\nProblem{neg}solved.')
    print(f'Mean score over {n_episodes} episodes: {average_score}')
    print(f'Failed episodes: {failures}')
    return solved


def train_agent(n_steps: int = 500000, render: bool = True, early_stop=True):
    env = ContinuousCartPoleEnv() if not COMPLEXENV else BipedalWalker()
    env.seed(np.random.randint(9999))
    tensorboard_path = os.path.join(".", "tensorboard")
    ensure_path(tensorboard_path)
    tensorboard_path = os.path.join(tensorboard_path, NAME)
    ensure_path(tensorboard_path)
    solved_score = 1800 if not COMPLEXENV else 250

    # we need to create the Tensorboard network BEFORE the agent, otherwise it gets angry
    # this could be done better, but oh well.

    train_dict_keys = ["score", "loss", "expl"] if not HIERARCHY else [
        "hi_score", "hi_loss", "hi_expl", "lo_score", "lo_loss", "lo_expl"
    ]
    tensorboard = Evaluation(tensorboard_path, train_dict_keys)

    if not HIERARCHY:
        # create new naive agent
        agent = DDPGAgent.new_trainable_agent(
            state_space=env.observation_space,
            action_space=env.action_space,
            exploration_mode="gaussian",
            exploration_magnitude=2.,
            exploration_decay=0.99999,
            learning_rate_actor=0.001,
            learning_rate_critic=0.001,
        )
    else:
        hi_action_space = gym.spaces.Box(
            low=np.negative(np.array(HI_ACTION_LIMITS[COMPLEXENV])),
            high=np.array(HI_ACTION_LIMITS[COMPLEXENV]),
            dtype=env.observation_space.dtype)

        agent = MetaAgent(
            env.observation_space,
            env.action_space,
            hi_agent_cls=DDPGAgent,
            lo_agent_cls=DDPGAgent,
            hi_action_space=hi_action_space,
            c=10,
        )

    total_steps, ep = 0, 0

    while total_steps < n_steps:
        steps, hi_steps, score, lo_score, done, lo_loss_sum, hi_loss_sum = 0, 0, 0, 0, False, 0, 0
        state = env.reset()
        if HIERARCHY:
            agent.reset_clock()

        ep += 1

        while not done and steps < MAX_STEPS_PER_EP:
            steps += 1
            action = agent.act(state=state)

            if HIERARCHY:
                goal_state = np.squeeze(state + agent.goal)

            if render:
                if not HIERARCHY:
                    env.render()
                else:
                    env.render(goal_state=goal_state)

            scaled_action = agent.scale_action(action)
            next_state, reward, done, _ = env.step(
                np.squeeze(scaled_action, axis=0))

            if steps >= MAX_STEPS_PER_EP:
                reward -= 1
                done = True  #Is this reasonable? Probably

            lo_loss, hi_loss = agent.train(state, action, reward, next_state,
                                           done)
            # this is the single loss if DDPG, or the lo_loss if hierarchical
            lo_loss_sum += (1 / steps) * (
                lo_loss - lo_loss_sum
            )  # avoids need to divide by num steps at end

            if HIERARCHY:
                agent.goal = agent.goal_transition(agent.goal, state,
                                                   next_state)

            if hi_loss is not None:
                hi_steps += 1
                hi_loss_sum += (1 / hi_steps) * (
                    hi_loss - hi_loss_sum
                )  # avoids need to divide by num steps at end

            score += reward
            state = next_state

            if HIERARCHY:
                lo_score += agent.lo_reward

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
                        agent.modify_exploration_magnitude(
                            0.1, mode='increment')
                    # 'd' will decrease the exploration factor
                    elif line == 'd':
                        agent.modify_exploration_magnitude(
                            -0.1, mode='increment')
                    # 'z' will zero the exploration factor
                    elif line == 'z':
                        agent.modify_exploration_magnitude(0.0, mode='assign')
                    # an empty line means stdin has been closed
                    else:
                        print('unknown command')

        total_steps += steps

        if not HIERARCHY:
            print(
                f' Episode {ep:4d}. Steps: {steps:4d}, Score: {score:4f}, Loss: {lo_loss_sum:.3f},'
                + f' Expl: {agent.explr_magnitude:6f}, ' +
                f' Global step: {total_steps} of {n_steps} ({(total_steps*100/n_steps):.2f}%)'
            )
            tensorboard.write_episode_data(
                ep,
                eval_dict={
                    "score": score,
                    "loss": lo_loss_sum,
                    "expl": agent.explr_magnitude,
                })
        else:
            print(
                f'Episode {ep:4d}, score: {score:.1f}, lo_score: {lo_score:.2f} '
                + f'steps: {steps:4d}, ' + f'lo_loss: {lo_loss_sum:.3f}, ' +
                f'hi_loss: {hi_loss_sum:.3f}, ' +
                f'lo_expl: {agent.lo_agent.explr_magnitude:6f}, ' +
                f'hi_expl: {agent.hi_agent.explr_magnitude:6f}, ' +
                f'Global step: {total_steps} of {n_steps} ({(total_steps*100/n_steps):.2f}%)'
            )
            tensorboard.write_episode_data(
                ep,
                eval_dict={
                    "hi_score": score,
                    "hi_loss": hi_loss_sum,
                    "hi_expl": agent.hi_agent.explr_magnitude,
                    "lo_score": lo_score,
                    "lo_loss": lo_loss_sum,
                    "lo_expl": agent.lo_agent.explr_magnitude,
                })

        if ep % 100 == 0:
            agent.save_model(saved_models_dir)

        #Early stop test
        if early_stop and score > 0.8 * solved_score:
            print(
                f'\n\n The agent reached a score of {score} while training. It is now eligible for an early stop test.'
            )
            print('Initiating tests...')
            agent.save_model(saved_models_dir)
            if isSolved(min_score=solved_score):
                return

    agent.save_model(saved_models_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--name",
        default="default",
        type=str,
        help="sets the folder name under which mode/tboard files will be saved"
    )
    parser.add_argument(
        "--steps",
        default=1000000,
        type=int,
        help="number of steps to train for")
    parser.add_argument(
        "--hier",
        action="store_true",
        default=False,
        help="Run Hierarchical (rather than DDPG)")
    parser.add_argument(
        "--walker",
        action="store_true",
        default=False,
        help="Run Bipedal Walker (rather than CCP)")
    parser.add_argument(
        "--render", action="store_true", default=False, help="show window")
    args = parser.parse_args()

    # global settings
    NAME = args.name
    COMPLEXENV = args.walker
    HIERARCHY = args.hier
    RENDER = args.render
    MAX_STEPS_PER_EP = 2000

    # print(args)
    #override here for ease of testing
    # COMPLEXENV = True
    # HIERARCHY = True
    #RENDER = True

    saved_models_dir = os.path.join('.', 'saved_models')
    ensure_path(saved_models_dir)
    saved_models_dir = os.path.join(saved_models_dir, NAME)
    ensure_path(saved_models_dir)

    # Fixing seed for comparing features
    np.random.seed(0)

    train_agent(n_steps=args.steps, render=RENDER)
    test_agent()
