"""Memory-Corruption Experiment Harness (mcx).

A controlled experiment that tests whether an incorrect memory (m_1) can
influence the creation of a second harmful memory (m_2), and whether that
second memory keeps affecting the agent after m_1 is deleted.

The experiment uses a language model (Qwen, or a deterministic scripted
stand-in) for exactly two operations:

    1. Generate a plan from a task + retrieved memories.
    2. Write one short lesson from a trajectory + feedback.

Everything else -- task selection, memory retrieval, environment execution,
true-outcome calculation, feedback, archive changes, logging, evaluation --
is controlled by Python. The model never decides whether its own plan
succeeded.
"""

__version__ = "0.1.0"
