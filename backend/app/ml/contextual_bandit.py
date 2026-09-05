"""
Contextual Bandit — Thompson Sampling for RecoverOS.

Action space: retry_now, retry_delayed, switch_to_upi, send_payment_link,
              whatsapp_nudge, email_reminder, sms_reminder, offer_discount,
              escalate_human, stop.

Uses Beta(α, β) priors per (segment, action) pair.
Combines Thompson-sampled exploration with utility scores for final selection.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

import numpy as np

from app.models.base import ActionType, CustomerSegment


# All actions except STOP (STOP is the do-nothing baseline)
ALL_ACTIONS = [a.value for a in ActionType if a != ActionType.STOP]

# All customer segments
ALL_SEGMENTS = [s.value for s in CustomerSegment]


class BanditArm:
    """Single arm of the Thompson Sampling bandit."""

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.alpha = alpha  # successes + prior
        self.beta = beta    # failures + prior
        self.total_reward = 0.0
        self.count = 0

    def sample(self, rng: np.random.Generator) -> float:
        """Sample from the Beta posterior."""
        return float(rng.beta(self.alpha, self.beta))

    def update(self, reward: float) -> None:
        """Update posterior with observed reward (0-1 scale)."""
        self.count += 1
        self.total_reward += reward
        if reward > 0:
            self.alpha += reward
        else:
            self.beta += (1.0 - reward)

    @property
    def mean(self) -> float:
        """Expected value (posterior mean)."""
        return self.alpha / (self.alpha + self.beta)

    def to_dict(self) -> dict:
        return {
            "alpha": round(self.alpha, 4),
            "beta": round(self.beta, 4),
            "mean": round(self.mean, 4),
            "count": self.count,
            "total_reward": round(self.total_reward, 4),
        }


class ContextualBandit:
    """
    Thompson Sampling contextual bandit for recovery action selection.

    Maintains separate Beta(α, β) distributions per (segment, action) pair.
    Combines exploration (Thompson sampling) with exploitation (utility scores)
    for balanced action selection.
    """

    def __init__(
        self,
        exploration_weight: float = 0.3,
        seed: int = 42,
    ):
        """
        Args:
            exploration_weight: Weight for Thompson sample vs utility score.
                0.0 = pure utility (no exploration)
                1.0 = pure Thompson sampling (no exploitation)
            seed: Random seed for reproducibility.
        """
        self.exploration_weight = exploration_weight
        self.rng = np.random.default_rng(seed)

        # Arms: {segment: {action: BanditArm}}
        self.arms: dict[str, dict[str, BanditArm]] = defaultdict(
            lambda: {action: BanditArm() for action in ALL_ACTIONS}
        )

        # Initialize all segments
        for seg in ALL_SEGMENTS:
            _ = self.arms[seg]  # trigger defaultdict creation

        # Log of all decisions for learning
        self.decision_log: list[dict] = []

    def select_action(
        self,
        segment: str,
        utility_scores: dict[str, float],
        available_actions: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        """
        Select the best action combining Thompson sampling exploration
        with utility-based exploitation.

        Args:
            segment: Customer segment (e.g., "vip", "regular")
            utility_scores: {action_type: net_expected_revenue} from UtilityEngine
            available_actions: Subset of actions to consider (None = all)

        Returns:
            (selected_action, selection_details)
        """
        if available_actions is None:
            available_actions = ALL_ACTIONS

        # Normalize utility scores to [0, 1] range
        if utility_scores:
            max_util = max(utility_scores.values()) if utility_scores else 1.0
            min_util = min(utility_scores.values()) if utility_scores else 0.0
            util_range = max_util - min_util if max_util != min_util else 1.0
        else:
            util_range = 1.0
            min_util = 0.0

        combined_scores = {}
        details = {}

        for action in available_actions:
            if action == ActionType.STOP.value:
                continue

            # Thompson sample
            arm = self.arms[segment][action]
            thompson_sample = arm.sample(self.rng)

            # Normalized utility
            raw_util = utility_scores.get(action, 0.0)
            norm_util = (raw_util - min_util) / util_range if util_range > 0 else 0.5

            # Combined score
            combined = (
                (1.0 - self.exploration_weight) * norm_util
                + self.exploration_weight * thompson_sample
            )

            combined_scores[action] = combined
            details[action] = {
                "thompson_sample": round(thompson_sample, 4),
                "utility_score": round(raw_util, 2),
                "normalized_utility": round(norm_util, 4),
                "combined_score": round(combined, 4),
                "arm_alpha": round(arm.alpha, 2),
                "arm_beta": round(arm.beta, 2),
                "arm_mean": round(arm.mean, 4),
                "arm_count": arm.count,
            }

        if not combined_scores:
            return ActionType.STOP.value, {"reason": "No valid actions available"}

        # Select best action
        best_action = max(combined_scores, key=combined_scores.get)

        selection_info = {
            "selected_action": best_action,
            "combined_score": round(combined_scores[best_action], 4),
            "exploration_weight": self.exploration_weight,
            "segment": segment,
            "all_scores": details,
        }

        return best_action, selection_info

    def update(
        self,
        segment: str,
        action: str,
        reward: float,
        context: Optional[dict] = None,
    ) -> None:
        """
        Update the bandit with observed outcome.

        Args:
            segment: Customer segment
            action: Action that was taken
            reward: Reward signal (0.0 = failure, 1.0 = full recovery, partial = proportional)
            context: Optional context dict for logging
        """
        if action in self.arms[segment]:
            self.arms[segment][action].update(reward)

        # Log the decision
        self.decision_log.append({
            "segment": segment,
            "action": action,
            "reward": reward,
            "context": context or {},
        })

    def get_state(self) -> dict:
        """Get full bandit state for persistence/inspection."""
        state = {}
        for segment, arms in self.arms.items():
            state[segment] = {}
            for action, arm in arms.items():
                state[segment][action] = arm.to_dict()
        return state

    def load_state(self, state: dict) -> None:
        """Load bandit state from persisted data."""
        for segment, arms in state.items():
            for action, arm_data in arms.items():
                arm = self.arms[segment][action]
                arm.alpha = arm_data.get("alpha", 1.0)
                arm.beta = arm_data.get("beta", 1.0)
                arm.count = arm_data.get("count", 0)
                arm.total_reward = arm_data.get("total_reward", 0.0)

    def get_segment_summary(self, segment: str) -> dict:
        """Get summary stats for a segment's arms."""
        arms = self.arms.get(segment, {})
        summary = {}
        for action, arm in arms.items():
            summary[action] = {
                "expected_reward": round(arm.mean, 4),
                "confidence": round(arm.count / (arm.count + 10), 4),  # simple confidence metric
                "observations": arm.count,
            }
        return summary

    def get_best_actions_by_segment(self) -> dict[str, str]:
        """Get the empirically best action per segment."""
        result = {}
        for segment in ALL_SEGMENTS:
            arms = self.arms[segment]
            best = max(arms.items(), key=lambda x: x[1].mean)
            result[segment] = {
                "action": best[0],
                "expected_reward": round(best[1].mean, 4),
                "observations": best[1].count,
            }
        return result


# Module-level singleton
contextual_bandit = ContextualBandit()
