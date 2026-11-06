// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// Community-funded lab testing. Each test request (keyed by its id) is a campaign:
/// contributors pool USD up to GOAL, a tester stakes STAKE to take the job, and must
/// submit the report within DEADLINE or anyone can slash the stake into the pool.
contract TestFund {
    enum Status { Open, Pending, Submitted }

    struct Campaign {
        uint256 pool;
        address tester;
        uint64 deadline;
        Status status;
    }

    uint256 public constant GOAL = 100e6;
    uint256 public constant STAKE = 50e6;
    uint256 public constant DEADLINE = 30 days;

    IERC20 public immutable usd;
    mapping(bytes32 => Campaign) public campaigns;
    mapping(bytes32 => mapping(address => uint256)) public contributed;

    event Contributed(bytes32 indexed id, address indexed from, uint256 amount);
    event Committed(bytes32 indexed id, address indexed tester, uint64 deadline);
    event ReportSubmitted(bytes32 indexed id, address indexed tester);
    event Slashed(bytes32 indexed id, address indexed tester);

    constructor(IERC20 usd_) {
        usd = usd_;
    }

    function contribute(bytes32 id, uint256 amount) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Open, "not open");
        require(amount > 0 && c.pool + amount <= GOAL, "bad amount");
        require(usd.transferFrom(msg.sender, address(this), amount), "transfer failed");
        c.pool += amount;
        contributed[id][msg.sender] += amount;
        emit Contributed(id, msg.sender, amount);
    }

    function commit(bytes32 id) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Open && c.pool >= GOAL, "not funded");
        require(usd.transferFrom(msg.sender, address(this), STAKE), "transfer failed");
        c.tester = msg.sender;
        c.deadline = uint64(block.timestamp + DEADLINE);
        c.status = Status.Pending;
        emit Committed(id, msg.sender, c.deadline);
    }

    // ponytail: status flip only; pool + stake stay locked until ZK report verification pays them out.
    function submitReport(bytes32 id) external {
        Campaign storage c = campaigns[id];
        require(c.status == Status.Pending && msg.sender == c.tester, "not your job");
        require(block.timestamp <= c.deadline, "deadline passed");
        c.status = Status.Submitted;
        emit ReportSubmitted(id, msg.sender);
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
}
