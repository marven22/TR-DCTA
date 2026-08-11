"""Real Qwen backend via HuggingFace transformers.

Loads a pinned Qwen checkpoint, runs in non-thinking mode with greedy decoding,
and returns the raw decoded text. Requires the pinned dependencies in
``requirements.txt`` (Python 3.10-3.12).

Device selection is automatic: CUDA if present, else Apple MPS (M-series GPU),
else CPU. Override with the MCX_DEVICE environment variable.

The harness never asks this backend whether the plan succeeded -- it only asks
for a plan and a lesson, exactly like the scripted backend.
"""
from __future__ import annotations

import os
from typing import List, Optional

from ..config import Config
from .base import GenerationRequest, ModelBackend

_SYSTEM_PROMPT = (
    "You are a careful agent. Follow the instructions exactly and return only "
    "the requested JSON with no extra commentary."
)


def _pick_device() -> str:
    import torch

    override = os.environ.get("MCX_DEVICE")
    if override:
        return override
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class QwenHFBackend(ModelBackend):
    name = "qwen"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None
        self._tokenizer = None
        self._device = None
        self._load()

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._device = _pick_device()
        # Allow unsupported MPS ops to fall back to CPU instead of crashing.
        if self._device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

        # The default revision is pinned to the default 7B checkpoint; if the
        # caller points at a different checkpoint we don't force that SHA.
        revision: Optional[str] = self.config.model_revision or None

        dtype = {
            "cuda": torch.bfloat16,
            "mps": torch.float16,   # fp16 is the safe MPS choice on torch 2.4.x
            "cpu": torch.float32,
        }[self._device]

        print(f"[qwen] loading {self.config.model_checkpoint} "
              f"(revision={revision or 'latest'}) on {self._device} ...")

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_checkpoint, revision=revision,
        )

        if self._device == "cuda":
            # Let accelerate shard across GPU(s).
            self._model = AutoModelForCausalLM.from_pretrained(
                self.config.model_checkpoint, revision=revision,
                torch_dtype=dtype, device_map="auto",
            )
        else:
            self._model = AutoModelForCausalLM.from_pretrained(
                self.config.model_checkpoint, revision=revision,
                torch_dtype=dtype,
            ).to(self._device)
        self._model.eval()

        # Make the model's default generation config genuinely greedy so the
        # checkpoint's sampling defaults (e.g. top_k=20) don't warn or leak in.
        if not self.config.generation.do_sample:
            gc = self._model.generation_config
            gc.do_sample = False
            gc.temperature = None
            gc.top_p = None
            gc.top_k = None

    def generate(self, request: GenerationRequest) -> str:
        return self.generate_batch([request])[0]

    def generate_batch(self, requests: List[GenerationRequest]) -> List[str]:
        import torch

        gen = self.config.generation
        texts = []
        for request in requests:
            messages = [
                {"role": "system", "content": request.system_prompt or _SYSTEM_PROMPT},
                {"role": "user", "content": request.prompt},
            ]
            # ``enable_thinking=False`` selects non-thinking mode on templates
            # that support it; older templates ignore the kwarg.
            try:
                text = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                    enable_thinking=gen.enable_thinking,
                )
            except TypeError:
                text = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            texts.append(text)
        old_padding_side = self._tokenizer.padding_side
        self._tokenizer.padding_side = "left"
        inputs = self._tokenizer(
            texts, return_tensors="pt", padding=True
        ).to(self._model.device)
        request_caps = [request.max_new_tokens for request in requests]
        max_new_tokens = max(
            (cap for cap in request_caps if cap is not None),
            default=gen.max_new_tokens,
        )
        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=gen.do_sample,      # False => greedy
                temperature=None if not gen.do_sample else gen.temperature,
                top_p=None if not gen.do_sample else gen.top_p,
                repetition_penalty=gen.repetition_penalty,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        self._tokenizer.padding_side = old_padding_side
        prefix = inputs["input_ids"].shape[1]
        return [text.strip() for text in self._tokenizer.batch_decode(
            output_ids[:, prefix:], skip_special_tokens=True
        )]
