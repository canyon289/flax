# Copyright 2021 The Flax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .. import struct

import jax.numpy as jnp
from jax import lax

import numpy as onp

from .base import OptimizerDef


@struct.dataclass
class _AdabeliefHyperParams:
  learning_rate: onp.ndarray
  beta1: onp.ndarray
  beta2: onp.ndarray
  eps: onp.ndarray
  weight_decay: onp.ndarray


@struct.dataclass
class _AdabeliefParamState:
  grad_ema: onp.ndarray
  deviation_sq_ema: onp.ndarray


class Adabelief(OptimizerDef):
  """Adabelief optimizer.

  Implements Adabelief - an adaptive method that modifies the stpesize according
  to the beleif in the current gradient prediction.  If the observed gradient
  deviates considerably from the prediciont, a small step is taken.  If the
  prediction and the observed graident agree, then a large step is taken.

  Reference: [Adabelief Optimizer: Adapting Stepsizes by the Belief in Ovserved
  Gradients](https://https://arxiv.org/pdf/2010.07468.pdf) (Zhuang et al, 2020).

  Attributes:
    learning_rate: The learning rate — the step size used to update the
      parameters.
    beta1: The exponentian decay rate for the 1st moment estimates. The
      coefficient used to calculate the first moments of the gradients (the
      moving average of the gradient) (default: 0.9).
    beta2: The exponentian decay rate for the 2nd moment estimates. The
      coefficient used to calculate the second moments of the gradients (the
      moving average of the gradient magnitude) (default: 0.999).
    eps: A small scalar added to the gradient magnitude estimate to improve
      numerical stability (default: 1e-8).
    weight_decay: The learning rate decay (default: 0.0).
  """

  def __init__(self,
               learning_rate=None,
               beta1=0.9,
               beta2=0.999,
               eps=1e-8,
               weight_decay=0.0):
    """Constructor for the Adabelief optimizer.

    Args:
      learning_rate: The step size used to update the parameters.
      beta1: The coefficient used for the moving average of the
        gradient (default: 0.9).
      beta2: The coefficient used for the moving average of the
        gradient magnitude (default: 0.999).
      eps: The term added to the gradient magnitude estimate for
        numerical stability (default: 1e-8).
      weight_decay: AdamW style weight decay rate
        (relative to learning rate) (default: 0.0).
    """
    hyper_params = _AdabeliefHyperParams(learning_rate, beta1, beta2, eps,
                                         weight_decay)
    super().__init__(hyper_params)

  def init_param_state(self, param):
    return _AdabeliefParamState(jnp.zeros_like(param), jnp.zeros_like(param))

  def apply_param_gradient(self, step, hyper_params, param, state, grad):
    assert hyper_params.learning_rate is not None, 'no learning rate provided.'
    beta1 = hyper_params.beta1
    beta2 = hyper_params.beta2
    weight_decay = hyper_params.weight_decay

    grad_ema = beta1 * state.grad_ema + (1. - beta1) * grad
    deviation_sq = lax.square(grad - grad_ema)
    deviation_sq_ema = beta2 * state.deviation_sq_ema + (
        1. - beta2) * deviation_sq + hyper_params.eps

    # bias correction
    t = jnp.array(step + 1, lax.dtype(param.dtype))
    grad_ema_corr = grad_ema / (1 - beta1 ** t)
    deviation_sq_ema_corr = deviation_sq_ema / (1 - beta2**t)

    denom = jnp.sqrt(deviation_sq_ema_corr) + hyper_params.eps
    new_param = param - hyper_params.learning_rate * grad_ema_corr / denom
    new_param -= hyper_params.learning_rate * weight_decay * param
    new_state = _AdabeliefParamState(grad_ema, deviation_sq_ema)
    return new_param, new_state
