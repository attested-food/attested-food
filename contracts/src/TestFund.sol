// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {EurekhaReportRegistry} from "eurekha/EurekhaReportRegistry.sol";

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// Community-funded lab testing. Each test request (keyed by its id) is a pool: contributors chip in
/// up to GOAL, and anyone can take the job at any time by staking STAKE. The tester posts a ZK proof of
/// the lab report (checked by EurekhaReportRegistry) within DEADLINE and receives the stake plus the
/// pool; whatever the pool was short of GOAL counts as the tester's own contribution. Late testers can be
/// slashed by anyone: the stake joins the pool and the job reopens. The admin later distributes revenue
/// (e.g. affiliate income) to a pool's contributors pro rata.
contract TestFund {
    enum Status { Open, Pending, Submitted }

    struct Campaign {
        uint256 pool;
        address tester;
        uint64 deadline;
        Status status;
        uint256 shares;
    }

    uint256 public constant GOAL = 100e6;
    uint256 public constant STAKE = 110e6;
    uint256 public constant DEADLINE = 30 days;

    IERC20 public immutable usd;
    EurekhaReportRegistry public immutable registry;
    address public immutable admin;

    mapping(bytes32 => Campaign) public campaigns;
    mapping(bytes32 => mapping(address => uint256)) public contributed;
    mapping(bytes32 => address[]) internal contributorList;
    /// keccak256(publicValues) of reports already used to close a pool.
    mapping(bytes32 => bool) public usedReport;

    event Contributed(bytes32 indexed id, address indexed from, uint256 amount);
    event Committed(bytes32 indexed id, address indexed tester, uint64 deadline);
    event ReportSubmitted(bytes32 indexed id, address indexed tester, bytes32 reportDigest, uint256 payout);
    event Slashed(bytes32 indexed id, address indexed tester);
    event Distributed(bytes32 indexed id, uint256 amount);

    constructor(IERC20 usd_, EurekhaReportRegistry registry_, address admin_) {
        usd = usd_;
        registry = registry_;
        admin = admin_;
    }

    function contributors(bytes32 id) external view returns (address[] memory) {
        return contributorList[id];
    }

    function contribute(bytes32 id, uint256 amount) external {
        Campaign storage c = campaigns[id];
        require(c.status != Status.Submitted, "closed");
        require(amount > 0 && c.pool + amount <= GOAL, "bad amount");
        require(usd.transferFrom(msg.sender, address(this), amount), "transfer failed");
        c.pool += amount;
        _share(id, c, msg.sender, amount);
        emit Contributed(id, msg.sender, amount);
    }

    function commit(bytes32 id) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Open, "taken");
        require(usd.transferFrom(msg.sender, address(this), STAKE), "transfer failed");
        c.tester = msg.sender;
        c.deadline = uint64(block.timestamp + DEADLINE);
        c.status = Status.Pending;
        emit Committed(id, msg.sender, c.deadline);
    }

    /// `backend`, `publicValues`, `proof`, `notarySignature`: a backend2-rs `sp1-groth16` artifact
    /// (the arguments of EurekhaReportRegistry.submit). Reverts unless the registry accepts the proof.
    // ponytail: proves a genuine lab report but not that it is for this pool's product; match the
    // committed product name/kv pairs against the request once requests carry an on-chain product key.
    function submitReport(
        bytes32 id,
        bytes32 backend,
        bytes calldata publicValues,
        bytes calldata proof,
        bytes calldata notarySignature
    ) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Pending && msg.sender == c.tester, "not your job");
        require(block.timestamp <= c.deadline, "deadline passed");
        bytes32 digest = keccak256(publicValues);
        require(!usedReport[digest], "report already used");
        registry.check(backend, publicValues, proof, notarySignature);
        usedReport[digest] = true;

        if (c.pool < GOAL) _share(id, c, msg.sender, GOAL - c.pool);
        uint256 payout = c.pool + STAKE;
        c.pool = 0;
        c.status = Status.Submitted;
        emit ReportSubmitted(id, msg.sender, digest, payout);
        require(usd.transfer(msg.sender, payout), "transfer failed");
    }

    /// After the deadline the stake is forfeited into the pool and the job reopens.
    function slash(bytes32 id) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Pending && block.timestamp > c.deadline, "not slashable");
        emit Slashed(id, c.tester);
        c.pool += STAKE;
        c.tester = address(0);
        c.deadline = 0;
        c.status = Status.Open;
    }

    /// Admin pays `amount` (pulled from the admin's wallet) to a tested pool's contributors, pro rata to
    /// what each put in. Rounding dust stays with the admin.
    // ponytail: one transfer per contributor in a loop; switch to claimable balances if pools get large.
    function distribute(bytes32 id, uint256 amount) external {
        require(msg.sender == admin, "not admin");
        Campaign storage c = campaigns[id];
        require(c.status == Status.Submitted && c.shares > 0, "not tested");
        address[] storage list = contributorList[id];
        for (uint256 i; i < list.length; i++) {
            uint256 part = amount * contributed[id][list[i]] / c.shares;
            if (part > 0) require(usd.transferFrom(msg.sender, list[i], part), "transfer failed");
        }
        emit Distributed(id, amount);
    }

    function _share(bytes32 id, Campaign storage c, address who, uint256 amount) internal {
        if (contributed[id][who] == 0) contributorList[id].push(who);
        contributed[id][who] += amount;
        c.shares += amount;
    }
}
