"""Integer stage-1 reference, without native code or transcript execution."""

P = 2**128 - 2**32 + 22537


def limbs(value):
    if not 0 <= value < P:
        raise ValueError("noncanonical Fp128")
    return [str(value % 2**64), str(value // 2**64)]


def lagrange(point):
    nodes = range(-4, 6)
    values = []
    for node in nodes:
        numerator = denominator = 1
        for other in nodes:
            if other != node:
                numerator = numerator * (point - other) % P
                denominator = denominator * (node - other) % P
        values.append(numerator * pow(denominator, -1, P) % P)
    return values


def row_forms(openings):
    if len(openings) != 35:
        raise ValueError("expected 35 rv64 openings")
    (
        left,
        right,
        product,
        branch,
        pc,
        upc,
        imm,
        address,
        rs1,
        rs2,
        rd,
        read,
        write,
        ll,
        rl,
        next_upc,
        next_pc,
        next_virtual,
        next_first,
        lookup,
        should_jump,
        add,
        sub,
        mul,
        load,
        store,
        jump,
        write_rd,
        virtual,
        assertion,
        no_update,
        advice,
        compressed,
        first,
        last,
    ) = openings
    guards = [
        load + store,
        1 - load - store,
        load,
        load,
        store,
        add + sub + mul,
        1 - add - sub - mul,
        add,
        sub,
        mul,
        1 - add - sub - mul - advice,
        assertion,
        write_rd,
        jump,
        should_jump,
        branch,
        1 - branch - jump,
        virtual - last,
        next_virtual - next_first,
    ]
    differences = [
        address - rs1 - imm,
        address,
        read - write,
        read - rd,
        rs2 - write,
        ll,
        ll - left,
        rl - left - right,
        rl - left + right - 2**64,
        rl - product,
        rl - right,
        lookup - 1,
        rd - lookup,
        rd - upc - 4 + 2 * compressed,
        next_upc - lookup,
        next_upc - upc - imm,
        next_upc - upc - 4 + 4 * no_update + 2 * compressed,
        next_pc - pc - 1,
        1 - no_update,
    ]
    return guards, differences


def terminal(tau, uniskip, remainder, openings):
    if not remainder or len(tau) != len(remainder) + 1:
        raise ValueError("wrong challenge dimensions")
    lu = lagrange(uniskip)
    lh = lagrange(tau[-1])
    kernel = sum(a * b for a, b in zip(lu, lh)) % P
    for t, r in zip(tau[:-1], reversed(remainder)):
        kernel = kernel * ((1 - t) * (1 - r) + t * r) % P
    weights = [0] * 19
    for i, row in enumerate([1, 2, 3, 4, 5, 6, 11, 14, 17, 18]):
        weights[row] = (1 - remainder[0]) * lu[i] % P
    for i, row in enumerate([0, 7, 8, 9, 10, 12, 13, 15, 16]):
        weights[row] = remainder[0] * lu[i] % P
    a, b = row_forms(openings)
    az = sum(w * v for w, v in zip(weights, a)) % P
    bz = sum(w * v for w, v in zip(weights, b)) % P
    return kernel * az * bz % P


def uniskip_evaluate(coefficients, point):
    if len(coefficients) > 28:
        raise ValueError("uni-skip degree exceeds 27")
    return sum(c * pow(point, i, P) for i, c in enumerate(coefficients)) % P


def uniskip_sum(coefficients):
    return sum(uniskip_evaluate(coefficients, node % P) for node in range(-4, 6)) % P


def chain_final(initial, compressed, challenges):
    if len(compressed) != len(challenges):
        raise ValueError("wrong round count")
    claim = initial
    for stored, r in zip(compressed, challenges):
        c0, c2, c3 = stored
        c1 = (claim - 2 * c0 - c2 - c3) % P
        claim = (c0 + c1 * r + c2 * r**2 + c3 * r**3) % P
    return claim
