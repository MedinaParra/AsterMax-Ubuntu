"""Verification-level preloaded joint coupling bolt clamp, unilateral contact and Coulomb friction.

This module is deliberately compact and auditable.  It represents one relative joint
DOF in the normal direction and one in the tangential direction.  The purpose is to
verify the coupled mechanics that AsterMax must preserve when bolt pretension is later
assembled into the full node-to-TRI3 solver:

    bolt pretension -> clamp force -> contact pressure resultant -> friction capacity
    -> stick/slip or interface opening.

Units follow the AsterMax PMV convention: mm and N.  Positive normal displacement
opens the interface; negative displacement is penalty penetration.  Positive
``normal_load_n`` is an external separating load.  Positive ``shear_load_n`` acts in
the positive tangential direction.

This is not a production bolted-joint/contact formulation and does not claim solid
bolt stresses, thread mechanics, flange bending or nonlinear material behaviour.
"""

from dataclasses import dataclass
from math import isfinite


class PreloadedJointError(ValueError):
    """Raised when a verification joint definition is physically invalid."""


@dataclass(frozen=True)
class PreloadedJoint:
    structural_normal_stiffness_n_per_mm: float
    bolt_axial_stiffness_n_per_mm: float
    contact_penalty_n_per_mm: float
    tangential_stick_stiffness_n_per_mm: float
    bolt_preload_n: float
    friction_coefficient: float


@dataclass(frozen=True)
class PreloadedJointResult:
    normal_displacement_mm: float
    tangential_displacement_mm: float
    bolt_force_n: float
    contact_normal_force_n: float
    friction_capacity_n: float
    friction_force_n: float
    normal_regime: str
    friction_regime: str
    clamp_retained: bool
    normal_residual_n: float
    tangential_residual_n: float


def _validate(joint: PreloadedJoint, normal_load_n: float, shear_load_n: float) -> None:
    values = (
        joint.structural_normal_stiffness_n_per_mm,
        joint.bolt_axial_stiffness_n_per_mm,
        joint.contact_penalty_n_per_mm,
        joint.tangential_stick_stiffness_n_per_mm,
        joint.bolt_preload_n,
        joint.friction_coefficient,
        normal_load_n,
        shear_load_n,
    )
    if not all(isfinite(float(v)) for v in values):
        raise PreloadedJointError("joint parameters and loads must be finite")
    if joint.structural_normal_stiffness_n_per_mm < 0.0:
        raise PreloadedJointError("structural normal stiffness must be non-negative")
    if joint.bolt_axial_stiffness_n_per_mm <= 0.0:
        raise PreloadedJointError("bolt axial stiffness must be positive")
    if joint.contact_penalty_n_per_mm <= 0.0:
        raise PreloadedJointError("contact penalty must be positive")
    if joint.tangential_stick_stiffness_n_per_mm <= 0.0:
        raise PreloadedJointError("tangential stick stiffness must be positive")
    if joint.bolt_preload_n < 0.0:
        raise PreloadedJointError("bolt preload must be non-negative")
    if joint.friction_coefficient < 0.0:
        raise PreloadedJointError("friction coefficient must be non-negative")


def solve_preloaded_joint(
    joint: PreloadedJoint,
    *,
    normal_load_n: float = 0.0,
    shear_load_n: float = 0.0,
) -> PreloadedJointResult:
    """Solve the two-DOF verification joint against independent closed-form branches.

    Normal equilibrium uses the sign convention

        (k_s + k_b) z + P0 + r_contact(z) = F_sep

    with ``r_contact = k_p*z`` only for ``z < 0``.  Therefore a positive preload
    closes the interface.  The open candidate is tested first; if it would penetrate,
    the closed penalty branch is used.

    Tangentially, an active contact supplies an elastic stick stiffness ``k_t`` until
    ``|F_t_trial| = mu*F_n``.  In slip, the friction force is capped at the Coulomb
    limit and acts against the imposed shear direction.  If the interface is open,
    friction is exactly zero.
    """
    _validate(joint, normal_load_n, shear_load_n)
    ks = float(joint.structural_normal_stiffness_n_per_mm)
    kb = float(joint.bolt_axial_stiffness_n_per_mm)
    kp = float(joint.contact_penalty_n_per_mm)
    kt = float(joint.tangential_stick_stiffness_n_per_mm)
    p0 = float(joint.bolt_preload_n)
    mu = float(joint.friction_coefficient)
    fsep = float(normal_load_n)
    fshear = float(shear_load_n)

    open_denominator = ks + kb
    if open_denominator <= 0.0:
        raise PreloadedJointError("normal system has no stiffness")
    z_open = (fsep - p0) / open_denominator
    if z_open >= 0.0:
        z = z_open
        normal_regime = "OPEN"
        contact_force = 0.0
    else:
        z = (fsep - p0) / (ks + kb + kp)
        normal_regime = "CLOSED"
        contact_force = -kp * z

    bolt_force = p0 + kb * z
    clamp_retained = bolt_force > 0.0
    friction_capacity = mu * contact_force

    if normal_regime == "OPEN" or contact_force == 0.0:
        # With no independent structural shear stiffness in this verification model,
        # a non-zero shear load on an open interface has no static equilibrium.
        if abs(fshear) > 0.0:
            raise PreloadedJointError("open interface cannot equilibrate shear load without a shear load path")
        ut = 0.0
        friction_force = 0.0
        friction_regime = "OPEN"
    else:
        trial_ut = fshear / kt
        trial_force = kt * trial_ut
        tolerance = 1e-12 * max(1.0, abs(trial_force), friction_capacity)
        if abs(trial_force) <= friction_capacity + tolerance:
            ut = trial_ut
            friction_force = -trial_force
            friction_regime = "STICK"
        else:
            # In ideal Coulomb slip, force is bounded but displacement is not determined
            # without another tangential stiffness/load path.  Report the displacement at
            # onset of slip, not a fabricated post-slip displacement.
            sign = 1.0 if fshear >= 0.0 else -1.0
            ut = sign * friction_capacity / kt
            friction_force = -sign * friction_capacity
            friction_regime = "SLIP"

    contact_residual = kp * z if normal_regime == "CLOSED" else 0.0
    normal_residual = (ks + kb) * z + p0 + contact_residual - fsep
    # Friction force here is the physical force exerted on the moving side, opposite
    # to shear.  In stick it must balance shear exactly.  In slip the residual is the
    # unbalanced shear that requires an additional structural/inertial load path.
    tangential_residual = fshear + friction_force

    return PreloadedJointResult(
        normal_displacement_mm=z,
        tangential_displacement_mm=ut,
        bolt_force_n=bolt_force,
        contact_normal_force_n=contact_force,
        friction_capacity_n=friction_capacity,
        friction_force_n=friction_force,
        normal_regime=normal_regime,
        friction_regime=friction_regime,
        clamp_retained=clamp_retained,
        normal_residual_n=normal_residual,
        tangential_residual_n=tangential_residual,
    )
