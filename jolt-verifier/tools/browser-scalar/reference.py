"""Integer-only reference for the pinned clear Boolean sumcheck scalar layer."""

P = 2**128 - 2**32 + 22537
MASK = 2**64 - 1


def limbs(value):
    if not 0 <= value < P:
        raise ValueError("noncanonical Fp128")
    return [str(value & MASK), str(value >> 64)]


def reconstruct(stored, claim):
    if not stored or not all(0 <= x < P for x in [*stored, claim]):
        raise ValueError("empty polynomial or noncanonical Fp128")
    return [stored[0], (claim - 2 * stored[0] - sum(stored[1:])) % P, *stored[1:]]


def evaluate(coefficients, point):
    # Direct powers, deliberately not the circuit's Horner implementation.
    return sum(c * pow(point, i, P) for i, c in enumerate(coefficients)) % P


def reduce_claim(initial, polynomials, challenges):
    if len(polynomials) != len(challenges):
        raise ValueError("wrong number of challenges")
    claims = [initial]
    for stored, challenge in zip(polynomials, challenges):
        claims.append(evaluate(reconstruct(stored, claims[-1]), challenge))
    return claims


def weighted_sum(values, weights):
    if len(values) != len(weights):
        raise ValueError("wrong number of weights")
    return sum(v * w for v, w in zip(values, weights)) % P


def batch_initial(values, weights, rounds, member_rounds):
    if len(values) != len(member_rounds) or not all(
        0 <= r <= rounds <= 255 for r in member_rounds
    ):
        raise ValueError("invalid batch dimensions")
    return weighted_sum(
        [v * pow(2, rounds - r, P) % P for v, r in zip(values, member_rounds)],
        weights,
    )
