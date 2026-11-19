# cdr-nv and ros2-nv in one program

`examples/ros2_interop/` is a program that uses both packages. cdr-nv
encodes a `std_msgs/Int32` and a `geometry_msgs/Twist` with its generated
structs; ros2-nv 0.1.1 opens a session with a Micro XRCE-DDS Agent over TCP,
asks the agent for the DDS entities, and sends each encoded message to its
data writer. A stock ROS 2 tool reads them: `ros2 topic echo` prints the
fields.

## Who does what

| Package | Part in the program |
| --- | --- |
| cdr-nv | `Int32.encode` and `Twist.encode` write the bytes into a `cdr.Writer`. `Int32.dds_type_name()` and `Twist.dds_type_name()` give the DDS type each topic is created with, and `type_name()` the ROS name the program prints. |
| ros2-nv | `rostransport.open_session`, `create_entity` and `write_sample` carry the session and the samples. `rosname.dds_topic_name` maps the ROS topic `/cdr_int32` to the DDS topic `rt/cdr_int32`. |

ros2-nv does not read a sample and cdr-nv does not know the agent, so the
program is the only place the two meet. That is why the example is a package
of its own (`examples/ros2_interop/novo.toml`): cdr-nv's `[dependencies]`
stays empty, and ros2-nv is a dependency of the example alone. The example
reaches cdr-nv by `path = "../.."` and ros2-nv by the registry range
`^0.1.1`.

**The sample is the message without its encapsulation header.** The agent
writes `00 01 00 00` in front of a sample itself, so the program writes with
`cdr.writer_le()` and sends the bytes after `cdr.HEADER_LEN`. Alignment is
counted from the end of the header, so the bytes after it are the same
whether or not the header is sent with them.

The two messages are cross-checked against the middleware: `rclpy` serialises
`Int32(data=1000)` and the first `Twist` of the run to the same bytes as the
program's first line below.

## The commands

In four terminals, with `source /opt/ros/jazzy/setup.bash` in the two that
use ROS 2. The port and the domain are the ones of the run below; the
defaults are 2018 and 0.

```
MicroXRCEAgent tcp4 --port 2078 -v 6
ROS_DOMAIN_ID=78 ros2 topic echo /cdr_int32 std_msgs/msg/Int32
ROS_DOMAIN_ID=78 ros2 topic echo /cdr_twist geometry_msgs/msg/Twist
cd examples/ros2_interop
ROS_DOMAIN_ID=78 novo run src/main.nv 127.0.0.1 2078
```

The program takes the agent's host and port as its arguments and the DDS
domain from `ROS_DOMAIN_ID`. It publishes ten pairs of messages, one pair a
second, after waiting one second for the agent's writers to find the
subscriptions.

## A run, 2026-11-19

Micro XRCE-DDS Agent 2.4.3, ROS 2 Jazzy with `rmw_fastrtps_cpp`, novo 0.26.0,
cdr-nv 0.1.1 and ros2-nv 0.1.1 from the registry, on one machine. Another
agent was already listening on port 2018 in domain 0, so the run uses port
2078 and domain 78.

The program printed:

```
session: established
participant: code 0, agent status 0 (ok)
publisher: code 0, agent status 0 (ok)
topic /cdr_int32: code 0, agent status 0 (ok)
datawriter /cdr_int32: code 0, agent status 0 (ok)
topic /cdr_twist: code 0, agent status 0 (ok)
datawriter /cdr_twist: code 0, agent status 0 (ok)
/cdr_int32: std_msgs/msg/Int32, /cdr_twist: geometry_msgs/msg/Twist
published 0: Int32 e8030000 code 0, Twist 000000000000e03f000000000000f4bf0000000000000040000000000000d03f000000000000e83f000000000000c0bf code 0
published 1: Int32 e9030000 code 0, Twist 000000000000f83f000000000000f4bf0000000000000040000000000000d03f000000000000e83f000000000000d0bf code 0
...
published 9: Int32 f1030000 code 0, Twist 0000000000002340000000000000f4bf0000000000000040000000000000d03f000000000000e83f000000000000f4bf code 0
```

`ros2 topic echo /cdr_int32 std_msgs/msg/Int32` printed `data: 1000` to
`data: 1009`, each followed by `---`. `ros2 topic echo /cdr_twist
geometry_msgs/msg/Twist` printed ten messages, the first and the last being:

```
linear:
  x: 0.5
  y: -1.25
  z: 2.0
angular:
  x: 0.25
  y: 0.75
  z: -0.125
---
...
linear:
  x: 9.5
  y: -1.25
  z: 2.0
angular:
  x: 0.25
  y: 0.75
  z: -1.25
---
```

During the run `ros2 topic list` showed `/cdr_int32` and `/cdr_twist`, and
`ros2 topic info -v /cdr_twist` showed one publisher, with the node name
`_CREATED_BY_BARE_DDS_APP_` and the QoS reliable and transient-local, and one
subscription, the type `geometry_msgs/msg/Twist` and the hash
`RIHS01_9c45bf16fe0983d80e3cfe750d6835843d265a9a6c46bd2e609fcddde6fb8d2a`,
which is `Twist.type_hash()`. The publisher's own type hash is shown as
`INVALID`, because the agent's writer does not send one.

The agent's log at level 6, reduced to its `info` lines:

```
create_client | create | client_key: 0xAABBCCDD, session_id: 0x81
establish_session | session established | client_key: 0xAABBCCDD, address: 127.0.0.1:41603
create_participant | participant created | client_key: 0xAABBCCDD, participant_id: 0x001(1)
create_publisher | publisher created | client_key: 0xAABBCCDD, publisher_id: 0x001(3), participant_id: 0x001(1)
create_topic | topic created | client_key: 0xAABBCCDD, topic_id: 0x001(2), participant_id: 0x001(1)
create_datawriter | datawriter created | client_key: 0xAABBCCDD, datawriter_id: 0x001(5), publisher_id: 0x001(3)
create_topic | topic created | client_key: 0xAABBCCDD, topic_id: 0x002(2), participant_id: 0x001(1)
create_datawriter | datawriter created | client_key: 0xAABBCCDD, datawriter_id: 0x002(5), publisher_id: 0x001(3)
delete_client | delete | client_key: 0xAABBCCDD
destroy_session | session closed | client_key: 0xAABBCCDD, address: 127.0.0.1:41603
```

The names are the part the agent does not check. A topic whose DDS name
lacks the `rt/` prefix, or whose type is not spelled
`<package>::msg::dds_::<Name>_`, is created without an error and `ros2 topic
echo` prints nothing; `docs/agent-run.md` of ros2-nv lists those and the other ways a run
fails.
