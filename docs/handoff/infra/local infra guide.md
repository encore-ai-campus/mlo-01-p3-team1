# 로컬 개발 인프라 아키텍처 가이드

## 1. 문서 목적

이 문서는 현재 프로젝트의 로컬 개발 인프라를 설명하기 위한 문서다.

주요 대상은 다음과 같다.

- Windows 물리 PC
- Hyper-V
- Ubuntu VM
- Kafka / Spark / Elasticsearch 3-node cluster
- 내부 가상 네트워크
- Windows WinNAT
- WireGuard
- SSH / ProxyJump
- 팀원 원격 접속 구조

이 문서를 읽으면 다음을 이해할 수 있어야 한다.

1. 왜 물리 PC 3대를 사용하고 있는가
2. 왜 각 PC에 Hyper-V VM을 3개씩 배치했는가
3. VM 간 통신은 어떤 IP를 사용하는가
4. WireGuard가 어디에 사용되는가
5. 팀원이 SSH로 각 VM에 어떻게 접속하는가
6. Windows Host / VM / WireGuard / SSH가 각각 어떤 역할을 맡는가

---

# 2. 전체 구성

현재 로컬 개발 환경은 **Windows 물리 PC 3대 + Hyper-V VM 9대**로 구성되어 있다.

```text
Physical PC 1
├── kafka-01
├── spark-01
└── es-01

Physical PC 2
├── kafka-02
├── spark-02
└── es-02

Physical PC 3
├── kafka-03
├── spark-03
└── es-03
```

각 물리 PC에는 서로 다른 서비스의 node를 하나씩 배치했다.

이 구조의 목적은 단순히 VM을 여러 개 만드는 것이 아니라, **실제 분산 시스템의 failure domain을 물리적으로 분리해서 테스트하기 위함**이다.

예를 들어 PC2가 완전히 종료되어도 다음 node들은 살아 있다.

```text
kafka-01
kafka-03

spark-01
spark-03

es-01
es-03
```

따라서 단순한 동일 PC 내부의 멀티 VM보다 실제 cluster 장애 테스트에 더 적합하다.

---

# 3. 물리 PC와 VM 역할

## PC1

```text
Windows Host
LAN IP: 192.168.0.102

Hyper-V VM
├── kafka-01 : 10.77.1.11
├── spark-01 : 10.77.1.12
└── es-01    : 10.77.1.13
```

PC1은 현재 가장 중요한 진입 지점이다.

특히 `spark-01`은 다음 역할을 가진다.

- Spark Master
- Spark Worker
- WireGuard gateway
- 팀원 SSH jump host
- PC2 / PC3 VM망으로 넘어가기 위한 관리망 gateway

---

## PC2

```text
Hyper-V VM
├── kafka-02 : 10.77.2.11
├── spark-02 : 10.77.2.12
└── es-02    : 10.77.2.13
```

---

## PC3

```text
Hyper-V VM
├── kafka-03 : 10.77.3.11
├── spark-03 : 10.77.3.12
└── es-03    : 10.77.3.13
```

---

# 4. 왜 Hyper-V를 사용하는가

최종 배포 환경은 AWS EC2 Linux 환경이지만, 개발 PC는 Windows다.

따라서 Windows에서 바로 Kafka / Spark / Elasticsearch cluster를 구성하는 것보다 Hyper-V 위에 Ubuntu VM을 만들어 사용하는 편이 실제 배포 환경과 더 유사하다.

주요 장점은 다음과 같다.

- Linux 기반 운영 환경 재현
- systemd 사용 가능
- SSH 기반 서버 관리 가능
- 네트워크 interface / route / firewall 실습 가능
- cluster node를 독립 서버처럼 다룰 수 있음
- AWS EC2 배포 시 환경 차이 감소

즉 Hyper-V VM은 단순한 개발 편의용이 아니라 **EC2 Linux 서버를 로컬에서 재현하기 위한 테스트 서버** 역할을 한다.

---

# 5. VM 내부 네트워크

각 Windows Host에는 VM 전용 내부 subnet이 존재한다.

```text
PC1 VM subnet
10.77.1.0/24

PC2 VM subnet
10.77.2.0/24

PC3 VM subnet
10.77.3.0/24
```

노드는 다음 주소를 사용한다.

| Role | PC1 | PC2 | PC3 |
|---|---|---|---|
| Kafka | 10.77.1.11 | 10.77.2.11 | 10.77.3.11 |
| Spark | 10.77.1.12 | 10.77.2.12 | 10.77.3.12 |
| Elasticsearch | 10.77.1.13 | 10.77.2.13 | 10.77.3.13 |

PC1 Windows Host는 VM 내부망에서 다음 주소를 가진다.

```text
10.77.1.1
```

예를 들어 PC1에서:

```powershell
ping 10.77.1.12
```

을 실행하면 `spark-01`에 직접 접근할 수 있다.

---

# 6. 왜 VM 주소를 10.77.x.x로 따로 사용하는가

초기에는 VM도 학교/사무실 LAN의 DHCP를 직접 사용하도록 구성했지만, upstream DHCP에서 서로 다른 VM에 중복 IP를 할당하는 문제가 발생했다.

따라서 VM 주소를 upstream DHCP에 맡기지 않고 다음처럼 독립적인 내부망으로 분리했다.

```text
Physical LAN
192.168.0.0/24

        +

Hyper-V Internal Network
10.77.x.0/24
```

이렇게 하면 VM 주소가 외부 DHCP 정책에 영향을 받지 않는다.

즉:

```text
VM IP = 우리가 직접 관리하는 안정적인 주소
Windows Host LAN IP = 실제 학교/사무실 네트워크에서 받는 주소
```

로 역할이 분리된다.

---

# 7. WinNAT의 역할

Hyper-V VM은 내부 subnet에 있기 때문에 외부 LAN에서 바로 접근할 수 없다.

PC1의 예:

```text
LAN
192.168.0.0/24

        |
        v

PC1 Windows
192.168.0.102
10.77.1.1

        |
        v

Hyper-V Internal Network
10.77.1.0/24
```

Windows의 `WinNAT`가 내부 VM과 외부 LAN 사이의 NAT 역할을 한다.

현재 PC1 NAT 이름:

```text
CLUSTER-NAT-PC1
```

내부 prefix:

```text
10.77.1.0/24
```

---

# 8. WireGuard port forwarding

팀원 PC는 `spark-01`의 WireGuard와 통신해야 한다.

하지만 `spark-01`은 직접 LAN IP를 가진 것이 아니라:

```text
10.77.1.12
```

라는 Hyper-V 내부 IP를 사용한다.

따라서 PC1 Windows가 UDP 51820을 `spark-01`로 전달한다.

```text
192.168.0.102:51820/UDP
            |
            | WinNAT Static Mapping
            v
10.77.1.12:51820/UDP
```

현재 mapping:

```text
Protocol        UDP
ExternalPort    51820
InternalIP      10.77.1.12
InternalPort    51820
```

즉 팀원은 실제로:

```text
192.168.0.102:51820
```

에 접속하지만 최종적으로 WireGuard packet은:

```text
spark-01
10.77.1.12:51820
```

에 도착한다.

---

# 9. WireGuard의 역할

WireGuard는 이 프로젝트에서 **서비스 데이터 통신용이 아니라 관리용 overlay network**로 사용한다.

주요 목적:

- 안정적인 관리 IP 제공
- 서로 다른 PC의 VM subnet 연결
- 팀원 SSH 접근
- 물리 LAN 구조와 VM 내부 IP 분리
- 관리 트래픽 암호화

WireGuard를 사용하면 실제 네트워크 위에 별도의 논리적 네트워크를 만들 수 있다.

```text
Physical Network
192.168.0.0/24

        ↓

WireGuard Overlay

        ↓

10.77.x.x VM networks
```

---

# 10. Spark VM 간 WireGuard mesh

현재 `spark-01`, `spark-02`, `spark-03`은 WireGuard peer 관계를 가진다.

WireGuard tunnel용 주소:

```text
spark-01 : 10.77.100.1
spark-02 : 10.77.100.2
spark-03 : 10.77.100.3
```

이 `10.77.100.x` 주소는 **Spark gateway끼리 연결하기 위한 transit/tunnel 주소**다.

팀원에게 할당하는 주소가 아니다.

예:

```text
spark-01
10.77.100.1
      |
      | WireGuard
      |
      +---------- spark-02
      |           10.77.100.2
      |
      +---------- spark-03
                  10.77.100.3
```

각 peer는 상대 PC의 VM subnet route도 가진다.

예를 들어 spark-01은:

```text
10.77.2.0/24
10.77.3.0/24
```

를 각각 spark-02 / spark-03 WireGuard peer를 통해 접근할 수 있다.

---

# 11. 기존 gateway mesh 예

spark-01에서:

```bash
sudo wg show clusterwg
```

예상 구조:

```text
interface: clusterwg
  listening port: 51820

peer: spark-02-public-key
  endpoint: 192.168.0.129:51820
  allowed ips:
    10.77.2.0/24
    10.77.100.2/32

peer: spark-03-public-key
  endpoint: 192.168.0.139:51820
  allowed ips:
    10.77.3.0/24
    10.77.100.3/32
```

따라서 spark-01에서:

```bash
ping 10.77.2.11
ping 10.77.3.13
```

과 같이 다른 물리 PC의 VM에도 접근할 수 있다.

---

# 12. 팀원 WireGuard 구조

팀원은 gateway mesh와 다른 WireGuard address range를 사용한다.

예:

```text
10.77.110.0/24
```

팀원마다 고유 `/32`를 할당한다.

예:

```text
encore2 -> 10.77.110.11/32
encore3 -> 별도 /32
encore4 -> 별도 /32
encore5 -> 별도 /32
```

팀원 PC의 WireGuard client는 기본적으로 gateway 하나만 접근한다.

```text
AllowedIPs = 10.77.1.12/32
```

즉 팀원 WireGuard가 cluster 전체 subnet을 직접 route하는 것이 아니다.

팀원에게는:

```text
WireGuard -> spark-01
```

경로만 열고,

그 이후 다른 VM 접속은 SSH ProxyJump를 사용한다.

---

# 13. 팀원 접속 전체 흐름

encore2를 예로 들면:

```text
encore2 Windows
LAN: 192.168.0.17
WG : 10.77.110.11
        |
        | WireGuard UDP 51820
        v
PC1 Windows
192.168.0.102
        |
        | WinNAT
        v
spark-01
10.77.1.12
        |
        | SSH ProxyJump
        |
        +------ kafka-01
        |
        +------ kafka-02
        |
        +------ kafka-03
        |
        +------ spark-02
        |
        +------ spark-03
        |
        +------ es-01 / es-02 / es-03
```

---

# 14. WireGuard와 SSH의 관계

WireGuard와 SSH는 역할이 다르다.

## WireGuard

```text
네트워크 연결을 만든다.
```

예:

```text
encore2
10.77.110.11

        ->

spark-01
10.77.1.12
```

즉 WireGuard는 **두 장비가 서로 통신할 수 있는 암호화된 network path**를 만든다.

---

## SSH

```text
그 네트워크를 통해 실제 Linux 서버에 로그인한다.
```

예:

```bash
ssh playdata@10.77.1.12
```

---

## SSH ProxyJump

팀원은 모든 VM에 WireGuard peer로 직접 연결하지 않는다.

대신:

```text
encore2
   |
   | WireGuard
   v
spark-01
   |
   | SSH forwarding
   v
kafka-02
```

형태로 접속한다.

따라서 spark-01은 **SSH Bastion / Jump Host 역할**도 수행한다.

---

# 15. 왜 모든 VM에 팀원 WireGuard peer를 등록하지 않는가

팀원마다 모든 서버에 WireGuard peer를 등록하면 관리 복잡도가 크게 증가한다.

예를 들어:

```text
4 team members
x
9 VMs
=
36 peer relationships
```

이 될 수 있다.

현재 구조에서는 팀원 peer를 gateway인 `spark-01`에만 등록한다.

```text
team member
     |
     v
spark-01
     |
     +---- other VMs
```

따라서 관리해야 할 peer 수가 훨씬 줄어든다.

---

# 16. SSH key 구조

WireGuard key와 SSH key는 완전히 다른 key다.

## WireGuard key

용도:

```text
VPN / network tunnel 인증 및 암호화
```

구성:

```text
WireGuard Private Key
WireGuard Public Key
```

팀원 Private Key는 팀원 PC 밖으로 보내지 않는다.

관리자는 팀원의 WireGuard Public Key만 등록한다.

---

## SSH key

용도:

```text
Linux SSH 로그인 인증
```

구성:

```text
id_ed25519
id_ed25519.pub
```

Private Key:

```text
id_ed25519
```

는 팀원 PC에만 보관한다.

Public Key:

```text
id_ed25519.pub
```

는 접속을 허용할 서버의:

```text
~/.ssh/authorized_keys
```

에 등록한다.

---

# 17. 팀원 등록 단계

팀원 등록은 반드시 두 단계로 나뉜다.

```text
BEFORE
   |
   v
ADMIN REGISTRATION
   |
   v
AFTER
```

---

## BEFORE

팀원 PC에서 key와 client config를 생성한다.

Windows:

```powershell
.\team-access-windows.ps1 prepare -Name encore2
```

macOS:

```bash
./team-access-macos.sh prepare --name encore5
```

이 과정에서 생성되는 관리자 전달용 파일:

```text
request.json
administrator-peer.conf
```

팀원은 이 두 파일만 관리자에게 전달한다.

---

# 18. 관리자 등록

관리자는 전달받은 정보로 `spark-01`을 설정한다.

주요 작업:

```text
1. WireGuard Public Key 등록
2. 팀원 /32 AllowedIPs 등록
3. 팀원 /32 return route 등록
4. SSH Public Key 등록
5. persistent WireGuard config 반영
```

예:

```text
encore2
WireGuard IP:
10.77.110.11/32
```

spark-01 route:

```bash
ip route get 10.77.110.11
```

정상 예:

```text
10.77.110.11 dev clusterwg src 10.77.100.1
```

---

# 19. AFTER

관리자 등록 완료 후에만 팀원이 tunnel을 활성화한다.

Windows:

```powershell
.\team-access-windows.ps1 activate -Name encore2
```

macOS:

```bash
./team-access-macos.sh activate --name encore5
```

연결 진단:

```powershell
.\team-access-windows.ps1 doctor -Name encore2
```

또는:

```bash
./team-access-macos.sh doctor --name encore5
```

---

# 20. 실제 SSH 접속

Windows:

```powershell
.\team-access-windows.ps1 ssh -Name encore2 -Node spark-01
```

다른 VM:

```powershell
.\team-access-windows.ps1 ssh -Name encore2 -Node kafka-01
.\team-access-windows.ps1 ssh -Name encore2 -Node kafka-02
.\team-access-windows.ps1 ssh -Name encore2 -Node spark-03
.\team-access-windows.ps1 ssh -Name encore2 -Node es-03
```

macOS:

```bash
./team-access-macos.sh ssh --name encore5 --node spark-01
```

---

# 21. SSH ProxyJump 개념

예를 들어 team member가 `kafka-02`에 접속한다고 가정한다.

논리적인 SSH 설정은 다음과 비슷하다.

```sshconfig
Host spark-01
    HostName 10.77.1.12
    User playdata
    IdentityFile ~/.ssh/id_ed25519

Host kafka-02
    HostName 10.77.2.11
    User playdata
    IdentityFile ~/.ssh/id_ed25519
    ProxyJump spark-01
```

실제 연결:

```text
team member
    |
    | SSH
    v
spark-01
    |
    | SSH forwarding
    v
kafka-02
```

따라서 team member가 `10.77.2.11`로 직접 route를 가지고 있지 않아도 된다.

---

# 22. 관리자가 확인할 WireGuard 명령

spark-01:

```bash
sudo wg show clusterwg
```

확인할 항목:

```text
peer
allowed ips
endpoint
latest handshake
transfer
```

팀원이 정상 접속하면 대략:

```text
peer: <member public key>
  endpoint: <member LAN IP>:<random UDP port>
  allowed ips: 10.77.110.x/32
  latest handshake: ...
  transfer: ...
```

가 나타난다.

---

# 23. 팀원이 확인할 WireGuard 명령

Windows:

```powershell
& "$env:ProgramFiles\WireGuard\wg.exe" show
```

정상 상태에서는:

```text
latest handshake
transfer received
transfer sent
```

가 모두 확인된다.

특히 다음 상태는 비정상이다.

```text
0 B received
sent only
latest handshake 없음
```

이는 client가 packet을 보내지만 서버와 handshake가 완료되지 않았다는 의미다.

---

# 24. WireGuard 연결 확인 순서

문제가 발생하면 아래 순서로 확인한다.

```text
1. tunnel service 실행 여부
2. client peer endpoint
3. client AllowedIPs
4. server peer 등록
5. server AllowedIPs
6. server return route
7. Windows WinNAT
8. Windows Firewall
9. spark-01 UDP 51820 listen
10. latest handshake
11. SSH TCP 22
```

---

# 25. PC1 WinNAT 확인 명령

```powershell
Get-NetNat
```

Static mapping:

```powershell
Get-NetNatStaticMapping
```

NAT session:

```powershell
Get-NetNatSession
```

현재 중요한 mapping:

```text
192.168.0.102:51820
       ->
10.77.1.12:51820
```

---

# 26. Windows Firewall 확인

```powershell
Get-NetFirewallRule |
    Where-Object DisplayName -match 'WireGuard|51820'
```

UDP 51820 inbound가 허용되어야 한다.

---

# 27. spark-01 확인 명령

WireGuard:

```bash
sudo wg show clusterwg
```

UDP listen:

```bash
sudo ss -lunp | grep ':51820'
```

SSH listen:

```bash
sudo ss -lntp | grep ':22'
```

route:

```bash
ip route
```

특정 팀원 route:

```bash
ip route get 10.77.110.11
```

---

# 28. packet level 문제 확인

spark-01:

```bash
sudo tcpdump -ni any udp port 51820
```

특정 LAN peer 제외:

```bash
sudo tcpdump -ni any \
'udp port 51820 and not host 192.168.0.129 and not host 192.168.0.139'
```

이를 통해 실제 UDP packet이 VM까지 도착하는지 확인할 수 있다.

---

# 29. cluster service 구조

관리 네트워크 위에서 실제 서비스 cluster가 동작한다.

## Kafka

```text
kafka-01
10.77.1.11

kafka-02
10.77.2.11

kafka-03
10.77.3.11
```

3-node KRaft cluster.

---

## Spark

```text
spark-01
10.77.1.12
Master + Worker

spark-02
10.77.2.12
Worker

spark-03
10.77.3.12
Worker
```

---

## Elasticsearch

```text
es-01
10.77.1.13

es-02
10.77.2.13

es-03
10.77.3.13
```

3-node Elasticsearch cluster.

---

# 30. 데이터 파이프라인에서의 위치

현재 전체 프로젝트의 서비스 흐름은 개략적으로:

```text
Data Source
    |
    v
Kafka Cluster
    |
    v
Spark Structured Streaming
    |
    v
Elasticsearch Cluster
    |
    v
Kibana / Application
```

WireGuard와 SSH는 이 데이터 경로에 직접 들어가는 것이 아니다.

```text
WireGuard / SSH
=
운영 / 관리 / 개발자 접근용 network
```

즉 Kafka message나 Spark streaming data가 팀원 WireGuard를 통해 흐르는 구조가 아니다.

---

# 31. Local과 AWS의 차이

현재 WireGuard + WinNAT 구조는 **로컬 Windows + Hyper-V 환경의 네트워크 문제를 해결하기 위한 구조**다.

AWS에서는 일반적으로:

```text
VPC
Private Subnet
Private IP
Security Group
```

을 사용하므로 VM subnet 연결을 위해 현재와 같은 Windows WinNAT가 필요하지 않다.

예:

```text
Local

Windows Host
   |
WinNAT
   |
Hyper-V VM
   |
WireGuard
```

AWS:

```text
VPC
 |
Private IP
 |
EC2
```

따라서 배포 스크립트는 가능한 한 실제 IP를 코드에 박지 않고 환경 설정 파일로 분리하는 것이 중요하다.

---

# 32. 현재 설계의 핵심 원칙

## 1. 서비스 node는 물리 PC마다 분산

```text
PC1 / PC2 / PC3
```

에 각각 Kafka / Spark / ES node 하나씩 배치한다.

---

## 2. VM IP는 외부 DHCP에 의존하지 않는다

```text
10.77.1.0/24
10.77.2.0/24
10.77.3.0/24
```

내부망을 사용한다.

---

## 3. WireGuard는 관리 overlay network

서비스 데이터 plane과 분리한다.

---

## 4. 팀원은 gateway 하나만 WireGuard로 접근

```text
team member
   |
WireGuard
   |
spark-01
```

---

## 5. 다른 VM 접근은 SSH ProxyJump

```text
team member
 -> spark-01
 -> target VM
```

---

## 6. Private Key는 절대 공유하지 않는다

공유 가능한 것:

```text
WireGuard Public Key
SSH Public Key
request.json
administrator-peer.conf
```

공유하면 안 되는 것:

```text
WireGuard Private Key
SSH Private Key
id_ed25519
cluster-team.conf
```

---

# 33. 장애 구간을 생각하는 방법

팀원이 VM에 SSH 접속하지 못할 경우 전체 경로를 한 번에 보지 말고 계층별로 분리해서 확인한다.

```text
[1] Physical LAN
encore2 -> PC1

[2] NAT
PC1 -> spark-01

[3] WireGuard
encore2 WG -> spark-01 WG

[4] Routing
spark-01 -> target subnet

[5] SSH
spark-01 -> target VM:22

[6] Authentication
SSH Public Key
```

이렇게 계층을 나누면 장애 위치를 빠르게 찾을 수 있다.

---

# 34. 핵심 한 줄 요약

현재 로컬 인프라는:

```text
Windows 물리 PC 3대
    ↓
Hyper-V Ubuntu VM 9대
    ↓
각 PC별 10.77.x.0/24 내부망
    ↓
Spark gateway 간 WireGuard mesh
    ↓
팀원은 spark-01에 WireGuard 접속
    ↓
SSH ProxyJump로 전체 VM 관리
```

구조다.

즉:

> **Hyper-V는 Linux 서버를 제공하고, WinNAT는 LAN과 VM 내부망을 연결하며, WireGuard는 관리용 사설 overlay network를 만들고, SSH ProxyJump는 그 위에서 실제 서버 접근을 담당한다.**
