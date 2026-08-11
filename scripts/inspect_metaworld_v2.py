"""One-time environment probe for the pinned Meta-World installation."""
import pkgutil

import gymnasium as gym
import metaworld
import metaworld.envs as environments


print("metaworld", getattr(metaworld, "__version__", metaworld.__file__))
print("environment_exports", [name for name in dir(environments) if name.isupper()])
print("policy_modules", [module.name for module in pkgutil.iter_modules(metaworld.__path__)
                         if "polic" in module.name])
try:
    import metaworld.policies as policies
    names = [name for name in dir(policies) if name.startswith("Sawyer")]
    print("policy_count", len(names), names[:20])
except Exception as exc:
    print("policy_error", repr(exc))
env = gym.make("Meta-World/MT1", env_name="reach-v3", seed=42)
observation, info = env.reset()
print("environment", observation.shape, info)
env.close()
