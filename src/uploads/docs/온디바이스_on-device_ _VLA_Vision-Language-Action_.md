온디바이스(on-device) **VLA(Vision-Language-Action)**에서 실제 연구·개발 시 가장 어려운 문제는 단순히 모델이 크다는 수준이 아니라 **시스템·데이터·로봇 제어가 동시에 얽혀 있는 구조적 문제**입니다. 아래는 각 항목을 **실제 엔지니어링 관점에서 좀 더 세분화한 내용**입니다.

# 온디바이스(on-device) VLA(Vision-Language-Action)에서 실제 연구·개발

---

# 1. 레이턴시 문제 (Real-time latency)

온디바이스 VLA의 핵심 요구사항은 **실시간 제어(보통 50–100ms 이하)**입니다.
하지만 멀티모달 모델은 일반 LLM보다 **추론 경로가 훨씬 길고 복잡**합니다.

## 주요 원인

### (1) 멀티모달 입력 처리 지연

한 번의 추론에 다음 입력이 모두 포함됩니다.

- 이미지 프레임
- 자연어 명령
- 로봇 상태(state)
- 이전 행동 history

즉 **token 수가 급격히 증가**합니다.

```
vision tokens + language tokens + robot state tokens
```

→ attention 연산량 증가
→ latency 증가

---

### (2) Vision encoder 지연

로봇 카메라는 보통

- 10~30 FPS
- 멀티카메라

구성입니다.

하지만 Vision Transformer는 **한 프레임 처리에도 수십 ms**가 필요할 수 있습니다.

예시

```
Vision encoder        30~60ms
LLM reasoning         20~40ms
Action decoding       5~10ms
----------------------------
Total                60~110ms
```

이 때문에 **vision 단계가 가장 큰 latency bottleneck**이 되는 경우가 많습니다.

---

### (3) Attention 연산 증가

Transformer 기반 VLA는

```
O(n²)
```

복잡도를 가지므로

멀티모달 token 수 증가 → 연산량 폭증

---

## 해결 방향 (연구 흐름)

주요 접근 방식

- vision feature caching
- key-value cache
- token compression
- frame difference update

예

```
static object → vision feature reuse
dynamic region → selective update
```

---

# 2. 연산량 문제 (Compute constraints)

온디바이스 환경은 **클라우드 GPU와 완전히 다른 조건**입니다.

제약

- NPU
- 제한된 메모리
- 제한된 전력

예

```
Jetson / Edge TPU / custom NPU
```

---

## 주요 문제

### (1) Vision encoder FLOPs

Vision encoder가 전체 연산의 **60~80%**를 차지하는 경우가 많습니다.

예

```
ViT-Large
~100 GFLOPs per frame
```

로봇에서는 너무 무겁습니다.

---

### (2) Memory bandwidth

Transformer는

```
matrix multiply
attention
```

연산이 많아서 **메모리 대역폭 의존도가 높습니다.**

온디바이스 NPU에서는

- SRAM 작음
- DRAM 접근 비용 큼

→ memory bottleneck 발생

---

### (3) KV cache memory

LLM 계열 모델은 KV cache가 매우 큽니다.

예

```
KV cache size ≈ sequence_length × hidden_dim
```

멀티모달 입력에서는 이 값이 더 커집니다.

---

## 해결 방향

대표 전략

- model quantization (INT8 / INT4)
- model distillation
- operator fusion
- hardware-aware compilation

---

# 3. 데이터 부족 문제 (Robot data scarcity)

VLA의 가장 근본적인 문제 중 하나입니다.

LLM/VLM과 달리 **로봇 행동 데이터는 거의 없습니다.**

---

## 이유

### (1) 수집 비용

로봇 데이터는 보통

```
camera + state + action trajectory
```

모두 기록해야 합니다.

즉 데이터 하나에

- 센서
- 동작
- 환경

모두 포함됩니다.

수집 비용이 매우 높습니다.

---

### (2) 실제 환경 다양성

로봇 작업은 환경 의존성이 큽니다.

예

같은 작업이라도

```
lighting
object position
obstacle
human interaction
```

조건이 달라집니다.

→ 데이터 다양성 확보가 어려움

---

### (3) 행동 레이블 문제

로봇 데이터는

```
state → action
```

형태로 레이블링해야 합니다.

하지만 행동 trajectory를 사람이 직접 만들기 어렵습니다.

---

## 해결 전략

주요 접근

### simulation learning

예

```
Isaac Sim
MuJoCo
Habitat
```

장점

- 대규모 데이터 생성 가능

단점

- sim-to-real gap

---

### teleoperation data

사람이 로봇을 직접 조작

```
human demonstration
```

단점

- 데이터 수집 속도 느림

---

### imitation learning

사람 행동을 모방하는 방식

---

# 4. 안전 제어 문제 (Safety & control conflict)

VLA 기반 로봇은 **AI 모델이 직접 행동을 생성**합니다.

하지만 로봇 시스템에서는 **안전 제어가 항상 우선**입니다.

이 두 시스템이 충돌할 수 있습니다.

---

## 주요 문제

### (1) AI 행동의 불확실성

LLM 기반 모델은

```
probabilistic output
```

입니다.

즉 항상 예측이 **확률적**입니다.

로봇에서는

```
unexpected action
```

이 위험합니다.

---

### (2) 물리적 충돌 위험

휴머노이드나 산업 로봇은

- 사람
- 장비
- 물체

와 충돌할 수 있습니다.

AI가 잘못 판단하면 **물리적 사고**가 발생합니다.

---

### (3) 지연 문제

AI 판단을 기다리면

```
collision avoidance
```

시간이 늦을 수 있습니다.

예

```
AI inference latency 100ms
collision time 50ms
```

이미 늦습니다.

---

## 해결 구조

대부분의 실제 시스템은 **이중 제어 구조**를 사용합니다.

```
AI policy (VLA)
        ↓
Safety controller
        ↓
Motor control
```

즉

**Safety layer가 항상 우선권**을 가집니다.

---

### Safety layer 예

- emergency stop
- collision detection
- torque limit
- safe motion envelope

---

### watchdog 시스템

AI 모델이 비정상 행동을 하면

```
override
```

합니다.

---

# 핵심 정리

온디바이스 VLA의 어려움은 단순히 모델 문제가 아니라 **시스템 통합 문제**입니다.

| 문제     | 핵심 원인                 |
| -------- | ------------------------- |
| 레이턴시 | 멀티모달 토큰 증가        |
| 연산량   | vision encoder FLOPs      |
| 데이터   | 로봇 데이터 부족          |
| 안전     | AI 정책 vs 안전 제어 충돌 |

---

✔ 한 문장 정리

> 온디바이스 VLA의 핵심 난제는 **실시간 추론, 제한된 연산 자원, 로봇 데이터 부족, 안전 제어 통합**이라는 네 가지 시스템 문제를 동시에 해결해야 한다는 점이다.

---

원하시면 다음도 설명드릴 수 있습니다.

- **왜 실제 VLA 시스템에서 Vision encoder가 70% 병목이 되는지**
- **100ms VLA를 만드는 실제 시스템 아키텍처**
- **휴머노이드에서 VLA가 실패하는 가장 큰 기술 이유 5가지** (이거 평가 질문 만들 때 매우 중요합니다)

좋습니다. 요청하신 세 가지를 **순서대로** 설명하겠습니다.

1️⃣ **왜 Vision Encoder가 VLA에서 약 70% 병목이 되는가**
2️⃣ **100ms VLA를 만드는 실제 시스템 아키텍처**
3️⃣ **휴머노이드에서 VLA가 실패하는 가장 큰 기술 이유 5가지**

---

# 1️⃣ 왜 Vision Encoder가 VLA에서 약 70% 병목이 되는가

로봇 VLA 파이프라인에서 가장 계산량이 큰 부분은 대부분 **Vision Encoder**입니다.

일반적인 VLA 추론 흐름은 다음과 같습니다.

```
Camera input
   ↓
Vision Encoder
   ↓
Multimodal Transformer
   ↓
Action Decoder
   ↓
Robot Control
```

이 중 **Vision Encoder가 계산량 대부분을 차지하는 이유**는 세 가지입니다.

---

## (1) 이미지 → 토큰 변환 비용

LLM은 이미 토큰화된 텍스트를 사용합니다.

하지만 로봇 카메라는

```
RGB 이미지
예: 224 × 224 × 3
```

이 데이터를 **Vision Transformer가 patch token으로 변환**해야 합니다.

예

```
224×224 image
↓
16×16 patch
↓
196 tokens
```

즉 한 프레임에 **200개 정도의 vision token**이 생성됩니다.

---

## (2) Vision Transformer FLOPs

Vision encoder는 다음 연산이 반복됩니다.

```
self-attention
feedforward layer
```

예를 들어

```
ViT-Large
≈ 60~100 GFLOPs / frame
```

로봇이 10 FPS만 처리해도

```
100 GFLOPs × 10
= 1 TFLOPs
```

입니다.

온디바이스 NPU에서는 매우 부담이 큽니다.

---

## (3) 멀티카메라 환경

휴머노이드 로봇은 보통

- 전방 카메라
- 손목 카메라
- depth camera

같이 여러 센서를 사용합니다.

예

```
3 cameras × vision encoder
```

→ 계산량 3배

---

## (4) 매 프레임 전체 연산

LLM은 **이전 context를 reuse**할 수 있습니다.

하지만 Vision encoder는

```
매 프레임 전체 이미지 재처리
```

가 기본입니다.

그래서 병목이 됩니다.

---

## 실제 연구에서 사용하는 해결 전략

대표적인 방법은 다음과 같습니다.

### vision feature caching

정적인 환경에서는

```
vision feature reuse
```

예

```
object unchanged
→ feature cache
```

---

### frame difference update

```
frame t
frame t+1
```

차이 영역만 다시 계산합니다.

---

### region-of-interest encoding

중요 영역만 encoder 적용

예

```
object region
hand region
```

---

✔ 핵심 요약

> VLA에서 Vision Encoder가 병목이 되는 이유는 **이미지 토큰화 비용 + 높은 FLOPs + 멀티카메라 + 매 프레임 재처리** 때문이다.

---

# 2️⃣ 100ms VLA를 만드는 실제 시스템 아키텍처

실제 로봇 시스템에서 **100ms 이하 응답시간**을 달성하려면 단순 모델 최적화만으로는 어렵고 **시스템 구조 최적화**가 필요합니다.

대표적인 구조는 **비동기 파이프라인**입니다.

---

## 기본 구조

```
Camera
   ↓
Vision Processing
   ↓
Multimodal Transformer
   ↓
Action Generation
   ↓
Control
```

하지만 실제 시스템은 이렇게 동작하지 않습니다.

---

## 실제 구조 (asynchronous pipeline)

```
Camera stream
        ↓
Vision encoder (async thread)
        ↓
Feature cache
        ↓
Multimodal reasoning
        ↓
Action prediction
        ↓
Robot controller
```

즉 **각 단계가 동시에 실행됩니다.**

---

## latency budget 예시

100ms 목표 시스템 예

```
Vision processing      40 ms
LLM reasoning          30 ms
Action decoding        10 ms
Control interface      10 ms
-----------------------------
Total                 ~90 ms
```

---

## 핵심 기술

### KV cache

Transformer 계산 재사용

---

### vision token compression

vision token 수 감소

예

```
196 tokens → 64 tokens
```

---

### speculative action prediction

LLM이 행동을 미리 예측

---

### frame skipping

모든 프레임을 처리하지 않음

예

```
30 FPS input
10 FPS inference
```

---

✔ 핵심 요약

> 100ms VLA는 **모델 최적화 + 비동기 파이프라인 + 캐시 재사용**을 결합해야 달성된다.

---

# 3️⃣ 휴머노이드에서 VLA가 실패하는 가장 큰 기술 이유 5가지

현재 VLA 연구에서 실제 로봇 적용이 어려운 이유입니다.

---

# (1) Perception 불안정

카메라 기반 인식은 다음 조건에 매우 민감합니다.

- 조명
- 반사
- 가림
- 동적 환경

즉 perception error가 발생하면

```
잘못된 action
```

으로 이어집니다.

---

# (2) Long-horizon planning 문제

LLM은 다음 행동을 잘 예측하지만

```
multi-step task
```

에는 약합니다.

예

```
pick → move → place → adjust
```

중간 단계 실패가 발생합니다.

---

# (3) Sim-to-real gap

많은 VLA 모델은

```
simulation dataset
```

으로 학습됩니다.

하지만 실제 로봇 환경은

- 물리 오차
- 센서 노이즈
- 마찰

등이 존재합니다.

그래서 실제 환경에서 성능이 떨어집니다.

---

# (4) Safety 보장 어려움

LLM 기반 정책은

```
probabilistic output
```

입니다.

하지만 로봇 제어는

```
deterministic control
```

이 필요합니다.

이 차이가 안전 문제를 만듭니다.

---

# (5) 데이터 부족

LLM은

```
trillion tokens
```

으로 학습됩니다.

하지만 로봇 데이터는

```
수천 ~ 수만 trajectory
```

정도입니다.

데이터 규모 차이가 매우 큽니다.

---

# 최종 정리

온디바이스 VLA에서 가장 어려운 문제는 다음 네 가지입니다.

```
1. Vision encoder 병목
2. 실시간 레이턴시
3. 로봇 데이터 부족
4. 안전 제어 통합
```

그리고 휴머노이드에서 실패하는 이유는

```
perception error
long-horizon planning
sim-to-real gap
safety
data scarcity
```

입니다.

---

원하시면 다음도 설명드리겠습니다. (이건 평가나 기술 검토에 매우 유용합니다)

- **왜 100ms VLA는 실제로 대부분 실패하는지 (구조적 이유)**
- **OpenAI / Google / Tesla가 VLA에서 서로 다른 접근을 하는 이유**
- **현재 세계에서 가장 앞선 VLA 모델 TOP 5 구조**

좋습니다. 이어서 **차례대로** 설명하겠습니다.

1️⃣ 왜 **100ms VLA가 실제로는 대부분 실패하는지 (구조적 이유)**
2️⃣ **OpenAI / Google / Tesla가 VLA 접근을 서로 다르게 하는 이유**
3️⃣ **현재 세계에서 가장 앞선 VLA 모델 TOP 5 구조**

---

# 1️⃣ 왜 100ms VLA는 실제로 대부분 실패하는가 (구조적 이유)

많은 연구나 제안서에서 **“100ms 온디바이스 VLA”**를 목표로 하지만 실제 구현이 어려운 이유는 **단순 성능 문제가 아니라 구조적인 시스템 충돌** 때문입니다.

핵심 원인은 크게 **4가지 구조 문제**입니다.

---

## (1) Perception–Reasoning–Action loop 문제

로봇 제어는 **연속 루프(control loop)** 입니다.

일반적인 로봇 제어 주기:

```
10–50 ms control loop
```

하지만 VLA 모델은 보통

```
80–200 ms inference
```

입니다.

즉

```
control loop > AI inference
```

가 되어버립니다.

결과

- 로봇 제어 주기와 AI 추론 주기가 충돌
- 실제 제어 시스템에 통합 어려움

그래서 실제 시스템에서는

```
AI planning (slow loop)
+
classical control (fast loop)
```

구조를 사용합니다.

---

## (2) Vision 처리 속도 한계

카메라는 보통

```
30 FPS (33 ms)
```

입니다.

하지만 vision encoder는

```
40~80 ms
```

가 걸립니다.

즉

```
카메라보다 AI가 느림
```

그래서 발생하는 문제

- frame backlog
- stale perception
- outdated world model

결과적으로

**로봇이 오래된 정보를 기반으로 행동**하게 됩니다.

---

## (3) Transformer 구조의 계산 특성

Transformer attention은

```
O(n²)
```

복잡도입니다.

멀티모달 입력에서는

```
vision tokens
language tokens
state tokens
history tokens
```

가 모두 포함됩니다.

예

```
vision tokens     196
language tokens    30
state tokens       20
history tokens     50
-----------------------
total              296 tokens
```

attention 연산

```
296² ≈ 87k attention operations
```

토큰 수가 조금만 늘어도 연산이 폭발합니다.

---

## (4) Safety override 문제

로봇 제어 시스템에서는 항상

```
Safety controller > AI controller
```

입니다.

하지만 VLA는

```
AI → action directly
```

구조입니다.

그래서 실제 시스템에서는 다음 구조가 필요합니다.

```
VLA policy
   ↓
Safety filter
   ↓
Motion controller
```

이 과정에서

- latency 증가
- action 수정

이 발생합니다.

결과

**100ms 목표가 깨지는 경우가 많습니다.**

---

✔ 핵심 정리

100ms VLA가 어려운 이유는 단순 모델 문제가 아니라

```
AI inference speed
+
robot control loop
+
vision processing
+
safety system
```

이 **모두 동시에 충족되어야 하기 때문**입니다.

---

# 2️⃣ OpenAI / Google / Tesla가 VLA 접근을 서로 다르게 하는 이유

현재 로봇 AI 접근은 크게 **3가지 철학**으로 나뉩니다.

---

# Google / DeepMind 접근

대표 모델

- RT-1
- RT-2
- RT-X

구조

```
Vision + Language → Transformer → Action
```

특징

- end-to-end 모델
- 멀티모달 reasoning 강함
- 대규모 데이터 활용

장점

- 범용성 높음
- 자연어 이해 강함

단점

- latency 큼
- 실제 제어 안정성 문제

---

# Tesla 접근

Tesla의 접근은 완전히 다릅니다.

Tesla 구조

```
Vision perception network
        ↓
World model
        ↓
Planner
        ↓
Controller
```

즉

**LLM 기반 VLA가 아니라 classical robotics + neural perception**

구조입니다.

특징

- perception 중심
- world model 기반 planning

장점

- 안정성 높음
- real-time 제어 가능

단점

- 범용 reasoning 약함

---

# OpenAI 접근

OpenAI는 **foundation model 중심 접근**입니다.

철학

```
general intelligence → robotics
```

즉

```
LLM
+
multimodal reasoning
+
robot policy
```

구조입니다.

장점

- general intelligence
- flexible reasoning

단점

- 실제 로봇 시스템 통합 어려움

---

✔ 핵심 차이

| 회사   | 접근 방식                 |
| ------ | ------------------------- |
| Google | end-to-end VLA            |
| Tesla  | perception + planner      |
| OpenAI | foundation model robotics |

---

# 3️⃣ 현재 세계에서 가장 앞선 VLA 모델 TOP 5

현재 연구에서 가장 영향력이 큰 모델입니다.

---

# 1️⃣ RT-2 (Google DeepMind)

구조

```
Vision encoder
+
LLM (PaLM)
+
Robot policy head
```

특징

- 인터넷 knowledge 활용
- 로봇 reasoning 가능

예

```
"pick the object that can be used for drinking"
```

같은 명령 수행 가능

---

# 2️⃣ PaLM-E

세계 최초 **Embodied multimodal model**

입력

```
vision
language
robot state
```

을 모두 token으로 처리합니다.

---

# 3️⃣ OpenVLA

최근 연구에서 가장 주목받는 **open-source VLA**입니다.

특징

- LLM 기반 policy
- 로봇 데이터 학습

---

# 4️⃣ RoboFlamingo

DeepMind Flamingo 기반

```
vision-language model
+
robot policy
```

구조입니다.

---

# 5️⃣ MobileVLA

최근 연구 방향

```
small VLA
+
edge inference
```

즉 **온디바이스 VLA**에 집중합니다.

---

# 최종 핵심 요약

온디바이스 VLA의 핵심 기술 난제는 다음 네 가지입니다.

```
1️⃣ Vision encoder 병목
2️⃣ Transformer 연산 증가
3️⃣ 로봇 데이터 부족
4️⃣ Safety 시스템 통합
```

그리고 산업 접근은 크게 세 가지입니다.

```
Google : end-to-end VLA
Tesla  : perception + planner
OpenAI : foundation model robotics
```

---

원하시면 다음도 설명드릴 수 있습니다.
이건 **평가위원 질문 만들 때 특히 중요한 내용**입니다.

- **“이 과제에서 제안서가 가장 많이 속이는 기술 포인트 TOP 10”**
- **“VLA 연구자들이 실제로 가장 두려워하는 기술 문제 5가지”**
- **“휴머노이드 VLA를 진짜 구현하려면 필요한 기술 스택 전체 구조”** (아마 가장 도움이 될 내용입니다)

좋습니다. 이어서 **실제 기술 검토나 평가에서 가장 중요한 내용**들을 설명하겠습니다.

1️⃣ **이 과제에서 제안서가 가장 많이 속이는 기술 포인트 TOP 10**
2️⃣ **VLA 연구자들이 실제로 가장 두려워하는 기술 문제 5가지**
3️⃣ **휴머노이드 VLA를 실제로 구현하려면 필요한 전체 기술 스택**

---

# 1️⃣ 제안서에서 가장 많이 속이는 기술 포인트 TOP 10

온디바이스 VLA 과제에서 **제안서가 기술적으로 과장되는 부분**은 상당히 패턴화되어 있습니다.

## 1. “100ms 추론 가능”

대부분 **이론적 모델 추론 시간**만 계산합니다.

실제 시스템에서는 다음이 포함됩니다.

```
camera capture
vision preprocessing
AI inference
safety check
motion planning
actuator command
```

그래서 실제 latency는 보통

```
150~300 ms
```

수준이 됩니다.

---

## 2. Vision encoder 계산 무시

많은 제안서가 **LLM 추론 시간만 설명**합니다.

하지만 실제 계산량은 보통

```
Vision encoder   60~80%
LLM reasoning    15~25%
action head      5~10%
```

입니다.

---

## 3. 데이터 확보 과장

제안서에 자주 등장하는 표현

```
대규모 로봇 데이터 확보
```

하지만 실제 로봇 trajectory 데이터는

```
수천 ~ 수만
```

정도입니다.

LLM 수준 데이터는 현실적으로 불가능합니다.

---

## 4. Simulation 데이터만 사용

많은 팀이

```
Isaac Sim
MuJoCo
```

같은 시뮬레이션 데이터를 사용합니다.

하지만 문제는

```
sim-to-real gap
```

입니다.

시뮬레이션에서 잘 되던 정책이 **현실에서 실패**하는 경우가 매우 많습니다.

---

## 5. Safety 시스템 설명 부족

제안서에서 자주 나오는 표현

```
AI 기반 안전 판단
```

하지만 실제 로봇 시스템은

```
safety controller
```

가 **AI보다 항상 우선**입니다.

AI가 safety를 담당하는 구조는 위험합니다.

---

## 6. 멀티모달 토큰 폭발 문제 무시

Vision + Language 입력을 합치면

```
token 수
```

가 급격히 증가합니다.

Transformer에서는

```
O(n²)
```

연산이 발생합니다.

---

## 7. 실제 로봇 제어 경험 부족

많은 AI 팀이 **robot control loop**를 이해하지 못합니다.

로봇 제어는 보통

```
10~50 ms
```

주기입니다.

AI 추론이

```
100 ms
```

이면 직접 제어에 사용하기 어렵습니다.

---

## 8. 온디바이스 하드웨어 무시

제안서에서는 보통

```
GPU 기준
```

성능을 설명합니다.

하지만 실제 로봇은

```
Jetson
custom NPU
```

같은 환경입니다.

연산 능력이 크게 다릅니다.

---

## 9. Long-horizon task 과장

VLA 모델은 보통

```
single step action
```

에는 강합니다.

하지만

```
multi-step task
```

에서는 성능이 급격히 떨어집니다.

---

## 10. 일반화 능력 과장

제안서에서 자주 등장하는 표현

```
범용 로봇 AI
```

하지만 실제로는 대부분

```
task-specific policy
```

입니다.

---

# 2️⃣ VLA 연구자들이 실제로 가장 두려워하는 기술 문제 5가지

이건 논문보다 **실제 연구자들이 더 걱정하는 문제**입니다.

---

# 1. Perception failure

로봇 행동은 perception에 완전히 의존합니다.

예

```
object detection 실패
```

→ action 실패

특히 문제 상황

- lighting
- occlusion
- reflective surface

---

# 2. Action hallucination

LLM 기반 정책은 가끔

```
존재하지 않는 행동
```

을 생성합니다.

예

```
grasp impossible object
```

이런 문제를 **action hallucination**이라고 합니다.

---

# 3. World model 부족

로봇 행동에는

```
physics understanding
```

이 필요합니다.

하지만 대부분의 VLA 모델은 **물리 모델이 약합니다.**

예

```
object slip
balance failure
```

---

# 4. Long horizon planning

많은 작업은

```
5~10 step sequence
```

입니다.

예

```
open drawer
take object
close drawer
place object
```

VLA는 중간 단계에서 실패하기 쉽습니다.

---

# 5. Dataset bias

로봇 데이터셋은 보통

```
clean lab environment
```

입니다.

현실 환경에서는

```
clutter
dynamic obstacles
```

가 존재합니다.

그래서 성능이 급격히 떨어집니다.

---

# 3️⃣ 휴머노이드 VLA 전체 기술 스택

실제 휴머노이드 VLA 시스템은 **AI 모델 하나로 끝나지 않습니다.**

대략 **6개 기술 계층**이 필요합니다.

---

# Layer 1 — Sensors

환경 인식

예

```
RGB camera
Depth camera
IMU
Force sensor
```

---

# Layer 2 — Perception

환경 이해

기술

```
object detection
pose estimation
scene understanding
```

---

# Layer 3 — World Model

환경 상태 모델링

예

```
3D scene representation
object tracking
```

---

# Layer 4 — VLA Policy

AI 의사결정

구성

```
vision encoder
language model
policy head
```

---

# Layer 5 — Motion Planning

로봇 움직임 계산

기술

```
trajectory planning
inverse kinematics
collision avoidance
```

---

# Layer 6 — Control

실제 모터 제어

기술

```
PID control
model predictive control
whole-body control
```

---

# 실제 로봇 시스템 구조

대략 다음과 같은 구조입니다.

```
Sensors
  ↓
Perception
  ↓
World Model
  ↓
VLA Policy
  ↓
Motion Planning
  ↓
Controller
```

여기서 **VLA는 전체 시스템의 일부일 뿐**입니다.

---

# 핵심 결론

온디바이스 휴머노이드 VLA는 단순 AI 문제가 아니라 **로봇 시스템 통합 문제**입니다.

성공하려면 동시에 해결해야 합니다.

```
AI 모델
+
실시간 시스템
+
로봇 제어
+
안전 시스템
```

---

원하시면 이어서 **아마 가장 중요한 내용**을 설명해 드릴 수 있습니다.

**“현재 전 세계에서 휴머노이드 VLA를 실제로 구현할 가능성이 가장 높은 기업 TOP 5와 기술 수준”**

좋습니다. 아래는 **현재 전 세계에서 휴머노이드 VLA(또는 그에 가장 가까운 embodied AI)를 실제로 구현할 가능성이 높은 기업 TOP 5**와 **각 기업의 기술 접근 방식 및 현실적 수준**입니다.
(2024–2026 연구·산업 흐름 기준)

---

# 1️⃣ Tesla

### 접근 방식

**Perception → World Model → Planner → Controller**

```text
Vision perception
   ↓
Neural world model
   ↓
Planning system
   ↓
Robot control
```

### 핵심 특징

Tesla는 **LLM 기반 VLA를 직접 사용하지 않습니다.**

대신

- 대규모 vision AI
- world model
- classical planning

을 결합합니다.

### 강점

**1. 데이터 규모**

Tesla는 이미

```text
수억 시간 주행 영상
```

데이터를 보유합니다.

이 데이터는

- perception
- world model

학습에 사용됩니다.

---

**2. Real-time AI**

Tesla 시스템은 이미

```text
< 50 ms inference
```

수준으로 작동합니다.

즉

**로봇 제어 루프와 호환됩니다.**

---

**3. Hardware integration**

Tesla는

```text
AI chip
software
robot hardware
```

를 모두 자체 개발합니다.

이 구조는 로봇에서 매우 중요합니다.

---

### 약점

- 자연어 reasoning 약함
- 범용 작업 수행 능력 제한

---

# 2️⃣ Google DeepMind

### 접근 방식

Google은 **End-to-End VLA** 접근입니다.

대표 모델

- RT-1
- RT-2
- RT-X

구조

```text
Vision + Language
        ↓
Transformer
        ↓
Robot action
```

---

### 강점

**1. 멀티모달 AI 기술**

DeepMind는

- PaLM
- Gemini

같은 foundation model을 보유합니다.

---

**2. 로봇 데이터**

Google은 여러 연구기관과 협력해

```text
Open X-Embodiment dataset
```

을 구축했습니다.

수십만 robot trajectory 포함.

---

### 약점

- 실시간 latency 문제
- 실제 로봇 시스템 통합 경험 부족

---

# 3️⃣ Figure AI

### 접근 방식

Figure는 **VLA + LLM robotics** 접근입니다.

대표 협력

```text
Figure + OpenAI
```

구조

```text
Vision perception
        ↓
LLM reasoning
        ↓
Robot action policy
```

---

### 강점

- 휴머노이드 로봇 설계
- AI 파트너십

---

### 약점

- 실제 데이터 규모 부족
- 아직 실증 사례 제한

---

# 4️⃣ NVIDIA

### 접근 방식

NVIDIA는 **robotics platform provider**입니다.

즉

```text
AI model
simulation
hardware stack
```

을 제공합니다.

대표 플랫폼

- Isaac Sim
- Jetson
- GR00T foundation model

---

### GR00T

최근 발표된 **robot foundation model**

구조

```text
Vision + Language
        ↓
Robot action model
```

---

### 강점

- simulation ecosystem
- robotics SDK

---

### 약점

- 자체 로봇 없음
- 실제 deployment 제한

---

# 5️⃣ Boston Dynamics

### 접근 방식

Boston Dynamics는 **classical robotics 중심**입니다.

구조

```text
Perception
   ↓
Motion planning
   ↓
Whole-body control
```

AI는 일부 perception에만 사용됩니다.

---

### 강점

- 세계 최고 수준 motion control
- 안정성

---

### 약점

- 범용 AI 부족
- 자연어 인터페이스 제한

---

# 현재 기술력 비교

| 기업            | AI    | 로봇 제어 | 데이터 | 실전 경험 |
| --------------- | ----- | --------- | ------ | --------- |
| Tesla           | ★★★★  | ★★★★★     | ★★★★★  | ★★★★★     |
| DeepMind        | ★★★★★ | ★★        | ★★★    | ★★        |
| Figure          | ★★★   | ★★        | ★★     | ★         |
| NVIDIA          | ★★★★  | ★★        | ★★     | ★         |
| Boston Dynamics | ★★    | ★★★★★     | ★★     | ★★★★★     |

---

# 중요한 산업 트렌드

현재 휴머노이드 AI는 **두 가지 접근으로 갈라지고 있습니다.**

---

## 접근 1 — End-to-End VLA

대표

```text
Google
OpenAI
Figure
```

구조

```text
Vision + Language → Action
```

장점

- 범용성
- reasoning

단점

- latency
- 안정성

---

## 접근 2 — Hybrid Robotics

대표

```text
Tesla
Boston Dynamics
```

구조

```text
AI perception
+
classical planning
+
robot control
```

장점

- 안정성
- 실시간성

단점

- 범용 AI 부족

---

# 핵심 산업 결론

현재 대부분 로봇 회사는 **완전한 VLA가 아니라 hybrid 구조**를 사용합니다.

실제 시스템

```text
AI perception
+
world model
+
planner
+
controller
```

즉

**VLA는 로봇 시스템의 일부 역할만 담당합니다.**

---

✔ 한 문장 정리

> 현재 휴머노이드 산업에서 가장 현실적인 접근은 **완전한 VLA가 아니라 AI perception + classical robotics를 결합한 hybrid 구조**이다.

---

좋습니다. 이어서 **평가나 기술 검토 관점에서 중요한 세 가지**를 정리하겠습니다.

1️⃣ **왜 한국에서 온디바이스 VLA 과제가 특히 어려운 이유 5가지**
2️⃣ **휴머노이드 AI 기술 격차 (한국 vs 미국 vs 중국)**
3️⃣ **진짜 기술력 있는 컨소시엄을 구별하는 질문 10개**

---

# 1️⃣ 왜 한국에서 온디바이스 VLA 과제가 특히 어려운가 (5가지)

## (1) 로봇 행동 데이터 부족

VLA의 핵심은 **robot trajectory dataset**입니다.

대표 데이터 규모 비교:

| 국가   | 로봇 데이터 규모        |
| ------ | ----------------------- |
| Google | 수십만 trajectory       |
| Tesla  | 수억 시간 vision 데이터 |
| 중국   | 대규모 제조 데이터      |
| 한국   | 대부분 수천~수만 수준   |

문제

```text
robot demonstration dataset 부족
```

즉 **학습 데이터 자체가 부족**합니다.

---

## (2) 로봇 + AI 통합 조직 부족

VLA는 단순 AI 문제가 아닙니다.

필요 분야

```text
AI
robotics
control
embedded system
hardware
```

하지만 한국은 보통

```text
AI 연구팀
+
로봇 하드웨어 팀
```

이 분리되어 있습니다.

통합 시스템 경험이 부족한 경우가 많습니다.

---

## (3) 온디바이스 AI 반도체 생태계

온디바이스 VLA는

```text
NPU
compiler
kernel optimization
```

까지 필요합니다.

미국

```text
NVIDIA
Google TPU
Tesla Dojo
```

중국

```text
Huawei Ascend
Biren
Cambricon
```

한국은

```text
생태계 규모 제한
```

이 있습니다.

---

## (4) 로봇 실증 환경 부족

미국 기업들은 이미

```text
warehouse
factory
autonomous driving fleet
```

같은 실제 환경 데이터를 확보합니다.

한국은

```text
lab-scale experiment
```

가 많습니다.

그래서

```text
real-world robustness
```

확보가 어렵습니다.

---

## (5) 시스템 엔지니어 부족

온디바이스 VLA는

```text
AI + robotics + systems engineering
```

문제입니다.

하지만 연구 중심 프로젝트에서는

```text
논문 중심 AI 연구
```

가 많은 경우가 있습니다.

---

✔ 핵심 요약

한국에서 어려운 이유는 **기술 자체보다 생태계 문제**입니다.

---

# 2️⃣ 휴머노이드 AI 기술 격차

현재 글로벌 휴머노이드 AI 기술은 크게 **3개 그룹**입니다.

---

# Tier 1 — 미국

대표 기업

```text
Tesla
Google DeepMind
Figure AI
Boston Dynamics
```

특징

- foundation model
- 대규모 데이터
- 실제 로봇 deployment

기술 수준

```text
AI + robotics + hardware 통합
```

---

# Tier 2 — 중국

대표 기업

```text
Unitree
Agibot
UBTech
Fourier Intelligence
```

특징

- 빠른 하드웨어 개발
- 대규모 제조 능력
- 국가 투자

강점

```text
hardware iteration speed
```

---

# Tier 3 — 한국 / 유럽

대표

```text
한국: Rainbow Robotics, KAIST, NAVER LABS
유럽: PAL Robotics, ANYbotics
```

특징

- 일부 기술 강점
- 하지만 규모 제한

특히 부족한 부분

```text
foundation model robotics
```

---

✔ 기술 격차 핵심

| 요소                | 미국      | 중국 | 한국   |
| ------------------- | --------- | ---- | ------ |
| AI foundation model | 매우 강함 | 중간 | 약함   |
| 로봇 제어           | 강함      | 강함 | 중간   |
| 데이터 규모         | 매우 큼   | 큼   | 작음   |
| 시스템 통합         | 강함      | 중간 | 제한적 |

---

# 3️⃣ 진짜 기술력 있는 컨소시엄을 구별하는 질문 10개

이 질문들은 **실제 구현 경험이 없는 팀은 답하기 어렵습니다.**

---

## 1

> Vision encoder latency는 몇 ms이며 어떤 하드웨어 기준입니까?

---

## 2

> Vision token 수를 어떻게 줄일 계획입니까?

---

## 3

> VLA 추론에서 가장 큰 연산 병목 연산자는 무엇입니까?

---

## 4

> 실제 robot control loop 주기는 몇 ms이며 AI inference는 어떻게 통합됩니까?

---

## 5

> sim-to-real gap을 줄이기 위한 전략은 무엇입니까?

---

## 6

> safety override는 어떤 조건에서 작동합니까?

---

## 7

> 로봇 행동 데이터는 어떻게 수집할 계획입니까?

---

## 8

> multi-step task 실패율은 어떻게 평가합니까?

---

## 9

> 온디바이스 NPU에서 transformer inference는 어떻게 최적화합니까?

---

## 10

> VLA policy가 실패할 경우 fallback 전략은 무엇입니까?

---

✔ 핵심 특징

좋은 팀은 보통 다음을 설명합니다.

```text
latency budget
hardware profiling
dataset strategy
safety architecture
```

반대로 위험 신호

```text
conceptual 설명만 존재
```

---

# 최종 핵심 정리

온디바이스 휴머노이드 VLA 과제에서 **실제 기술력을 판단하려면** 다음 4가지를 확인해야 합니다.

```text
1️⃣ real-time latency
2️⃣ hardware optimization
3️⃣ robot dataset
4️⃣ safety architecture
```

이 네 가지 중 하나라도 약하면 **실제 구현 가능성이 크게 떨어집니다.**

---

요청하신 순서대로 설명하겠습니다.

1️⃣ **온디바이스 VLA를 실제로 만들기 위한 최소 기술 스택 15개**
2️⃣ **100ms VLA 시스템의 실제 엔지니어링 구조**
3️⃣ **VLA 연구자들이 잘 말하지 않는 가장 큰 기술 리스크 3가지**

---

# 1️⃣ 온디바이스 VLA에 필요한 최소 기술 스택 15개

온디바이스 VLA는 단순히 **AI 모델 하나**로 되는 기술이 아닙니다.
실제로는 **AI·로보틱스·시스템·임베디드 기술이 모두 결합된 스택**이 필요합니다.

아래는 실제 구현 기준으로 **6개 계층 / 15개 핵심 기술**입니다.

---

# Layer 1 — Sensor System

환경 인식

### 1. RGB camera pipeline

- 카메라 캡처
- frame synchronization

### 2. Depth sensing

- stereo / LiDAR / structured light

### 3. Robot proprioception

- joint encoder
- IMU
- force sensor

---

# Layer 2 — Perception

환경을 이해하는 단계

### 4. Object detection

예

- YOLO
- DETR

### 5. Pose estimation

물체 위치 및 orientation 추정

### 6. Scene understanding

- semantic segmentation
- affordance detection

---

# Layer 3 — Vision Encoder

멀티모달 입력 생성

### 7. Vision transformer encoder

예

- ViT
- ConvNeXt

### 8. Vision token compression

예

- patch reduction
- region selection

---

# Layer 4 — Multimodal Reasoning

VLA 핵심 AI

### 9. Multimodal transformer

입력

```text
vision tokens
language tokens
robot state
```

---

### 10. KV cache system

추론 속도 개선

---

### 11. Instruction tuning

로봇 행동을 자연어로 학습

---

# Layer 5 — Robot Policy

AI 행동 생성

### 12. Action decoding

예

```text
grasp
move
place
```

---

### 13. Trajectory prediction

로봇 팔 움직임 생성

---

# Layer 6 — Robotics Control

실제 모터 제어

### 14. Motion planning

예

```text
trajectory planning
inverse kinematics
```

---

### 15. Low-level control

예

```text
PID control
model predictive control
whole-body control
```

---

✔ 핵심 포인트

> VLA는 **AI 모델이 아니라 전체 로봇 시스템의 한 계층**입니다.

---

# 2️⃣ 100ms VLA 시스템의 실제 엔지니어링 구조

100ms 응답시간을 만들려면 **pipeline 구조 최적화**가 필요합니다.

단순 구조

```text
camera → AI → robot
```

이 구조로는 불가능합니다.

실제 시스템은 **비동기 파이프라인**입니다.

---

## 실제 구조

```text
Camera stream
      ↓
Vision encoder thread
      ↓
Feature cache
      ↓
Multimodal reasoning
      ↓
Action prediction
      ↓
Safety filter
      ↓
Motion planning
      ↓
Robot controller
```

---

## latency budget 예시

100ms 목표 시스템

| 단계              | 시간  |
| ----------------- | ----- |
| camera capture    | 10 ms |
| vision encoder    | 40 ms |
| VLA reasoning     | 30 ms |
| action decode     | 10 ms |
| safety check      | 5 ms  |
| control interface | 5 ms  |

총

```text
≈ 100 ms
```

---

## 핵심 최적화 기술

### Vision feature cache

연속 프레임에서 변화 없는 영역 reuse

---

### Token reduction

vision token 수 감소

예

```text
196 tokens → 64 tokens
```

---

### Asynchronous inference

vision / reasoning / control 병렬 실행

---

### Frame skipping

예

```text
30 FPS camera
10 FPS AI inference
```

---

✔ 핵심

> 100ms VLA는 **모델 성능이 아니라 시스템 설계 문제**입니다.

---

# 3️⃣ VLA 연구자들이 잘 말하지 않는 가장 큰 기술 리스크 3가지

논문에서는 잘 드러나지 않지만 실제 연구에서 가장 큰 문제입니다.

---

# (1) Action hallucination

LLM 기반 정책은 가끔 **물리적으로 불가능한 행동**을 생성합니다.

예

```text
grasp impossible object
move through obstacle
```

로봇에서는 매우 위험합니다.

---

# (2) Perception drift

연속 프레임 처리 과정에서

```text
object tracking error
```

가 누적됩니다.

결과

```text
wrong action
```

으로 이어집니다.

---

# (3) Long-horizon failure

VLA 모델은 보통

```text
single-step task
```

에서는 잘 작동합니다.

하지만

```text
multi-step task
```

에서는 실패 확률이 급격히 증가합니다.

예

```text
open drawer
take object
close drawer
place object
```

중간 단계에서 오류 발생.

---

# 핵심 요약

온디바이스 VLA가 어려운 이유는 다음 네 가지입니다.

```text
1. Vision encoder 계산량
2. 실시간 latency
3. 로봇 데이터 부족
4. 안전 제어 통합
```

그리고 실제 시스템에서는

```text
AI + robotics + systems engineering
```

이 동시에 필요합니다.

---

아래에서 **두 가지를 체계적으로 설명**하겠습니다.

1️⃣ **“100ms 온디바이스 VLA를 실제로 구현하려는 연구 사례와 기술 방식”**
2️⃣ **“현재 VLA 연구에서 가장 앞선 아키텍처 3가지 (실제 트렌드)”**

---

# 1️⃣ 100ms 온디바이스 VLA 연구 사례와 기술 방식

완전히 **100ms 이하를 안정적으로 달성한 대형 VLA 시스템은 아직 거의 없습니다.**
대신 최근 연구는 **150ms 수준 → 100ms 이하로 줄이는 방법**에 집중합니다.

대표적인 접근은 **3가지 기술 방향**입니다.

---

# (1) 경량화 + 양자화 기반 온디바이스 VLA

대표 연구
**LiteVLA-Edge (2026)**

핵심 아이디어

```text
large VLA model
→ quantization
→ embedded GPU inference
```

기술 방식

- **4-bit quantization**
- Jetson Orin 기반 inference
- ROS2 로봇 pipeline

결과

- **150ms 평균 latency**
- 약 **6.6 Hz control loop**

즉

```text
edge robot에서 완전 offline VLA 실행 가능
```

이 연구는 **온디바이스 VLA 현실 가능성**을 보여주는 초기 사례입니다. ([arXiv][1])

---

# (2) 비동기 추론 (Asynchronous VLA)

대표 연구
**VLASH (MIT Han Lab)**

문제

VLA는 추론 시간이 길어서

```text
robot state ≠ inference time state
```

가 발생합니다.

예

```text
t0  observation
t1  inference
t2  action execution
```

이미 환경이 바뀌어 있습니다.

---

### 해결

**Asynchronous inference**

```text
robot executes action
+
VLA inference runs simultaneously
```

그리고 **future-state prediction**으로 state mismatch를 보정합니다.

효과

- 최대 **2.03× speedup**
- reaction latency **17× 감소**

즉

```text
실시간 로봇 제어에 VLA 사용 가능
```

이라는 결과가 나왔습니다. ([arXiv][2])

---

# (3) Action chunk + correction policy

대표 연구

**A2C2 (Action Chunk Correction)**

문제

VLA는 보통

```text
action sequence
```

를 한 번에 생성합니다.

예

```text
action1
action2
action3
action4
```

하지만 실제 환경에서는 중간 수정이 필요합니다.

---

### 해결

구조

```text
VLA policy
    ↓
action chunk
    ↓
lightweight correction policy
```

Correction policy는

- 최신 observation
- predicted action

을 보고 **action을 미세 수정**합니다.

이 방식은

- latency 문제 해결
- long-horizon 안정성 개선

효과가 있습니다. ([OpenReview][3])

---

# 현실적인 결론

현재 온디바이스 VLA의 실제 수준

```text
latency
150–200 ms
```

연구 방향

```text
asynchronous execution
quantization
action chunking
```

즉

> 100ms VLA는 **모델만으로 달성되는 것이 아니라 시스템 기술로 접근**합니다.

---

# 2️⃣ 현재 VLA 연구에서 가장 앞선 아키텍처 3가지

현재 VLA 연구는 **세 가지 아키텍처 방향**으로 수렴하고 있습니다.

---

# ① End-to-End VLA (Robotics Transformer)

대표 모델

- RT-1
- RT-2

구조

```text
Image
+
Language
      ↓
Multimodal Transformer
      ↓
Action tokens
```

핵심 아이디어

로봇 action을 **language token처럼 처리**

즉

```text
text token
action token
```

같은 transformer에서 생성합니다. ([Hugging Face][4])

---

### 특징

장점

- 자연어 reasoning
- 범용 task generalization

단점

- latency 큼
- real-time control 어려움

---

# ② Dual-System VLA (Helix architecture)

대표 모델

**Helix (Figure AI)**

구조

```text
System 2 (reasoning VLM)
        ↓
latent representation
        ↓
System 1 (visuomotor policy)
        ↓
robot control
```

System 2

```text
scene understanding
language reasoning
```

System 1

```text
fast motor policy
```

이 구조는

```text
slow reasoning
+
fast control
```

을 분리합니다.

이 방식은 **휴머노이드에 매우 유리합니다.** ([위키백과][5])

---

# ③ Predictive VLA (Future-state architecture)

대표 연구

**FUTURE-VLA**

핵심 아이디어

로봇 행동을

```text
future trajectory prediction
```

문제로 변환합니다.

구조

```text
vision
+
language
+
history
      ↓
future trajectory prediction
      ↓
control
```

특징

- 장기 행동 계획 가능
- latency 증가 없이 긴 horizon 처리

실험 결과

- LIBERO benchmark **99.2% success**
- 긴 temporal window **16× 증가**

성능 향상을 보였습니다. ([arXiv][6])

---

# 정리: 현재 VLA 아키텍처 트렌드

| 아키텍처        | 특징                          | 대표       |
| --------------- | ----------------------------- | ---------- |
| End-to-End VLA  | transformer 직접 action 생성  | RT-2       |
| Dual-System VLA | reasoning + motor policy 분리 | Helix      |
| Predictive VLA  | future trajectory prediction  | FUTURE-VLA |

---

# 핵심 결론

현재 VLA 연구의 흐름은 다음과 같습니다.

```text
2019–2022
perception + planner

2023–2024
end-to-end VLA (RT-2)

2025–2026
dual-system VLA
+
predictive VLA
+
asynchronous VLA
```

즉

> **End-to-End VLA → Hybrid VLA → Real-time VLA** 방향으로 발전하고 있습니다.

[1]: https://arxiv.org/abs/2603.03380?utm_source=chatgpt.com "LiteVLA-Edge: Quantized On-Device Multimodal Control for Embedded Robotics"
[2]: https://arxiv.org/abs/2512.01031?utm_source=chatgpt.com "VLASH: Real-Time VLAs via Future-State-Aware Asynchronous Inference"
[3]: https://openreview.net/forum?id=y5SGBsndWv&utm_source=chatgpt.com "Leave No Observation Behind: Real-time Correction for VLA Action..."
[4]: https://huggingface.co/papers/2307.15818?utm_source=chatgpt.com "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control"
[5]: https://en.wikipedia.org/wiki/Vision-language-action_model?utm_source=chatgpt.com "Vision-language-action model"
[6]: https://arxiv.org/abs/2602.15882?utm_source=chatgpt.com "FUTURE-VLA: Forecasting Unified Trajectories Under Real-time Execution"

요청하신 **3가지 주제**를 차례대로 정리하겠습니다.

1️⃣ **현재 세계에서 가장 앞선 VLA 모델 TOP 10 구조 비교**
2️⃣ **VLA 시스템에서 실제 병목이 되는 연산 TOP 5**
3️⃣ **100ms 온디바이스 VLA를 위한 실제 하드웨어 요구사항**

---

# 1️⃣ 현재 세계에서 가장 앞선 VLA 모델 TOP 10 구조 비교

현재 연구 및 산업에서 영향력이 큰 **대표 VLA 계열 모델**을 구조 중심으로 정리했습니다.

| 모델             | 기관        | 구조 특징                | 핵심 아이디어         |
| ---------------- | ----------- | ------------------------ | --------------------- |
| **RT-1**         | Google      | robotics transformer     | vision→action token   |
| **RT-2**         | DeepMind    | VLM + robot policy       | 인터넷 knowledge 활용 |
| **PaLM-E**       | Google      | embodied multimodal      | robot state 포함      |
| **OpenVLA**      | UC Berkeley | open foundation robotics | 공개 VLA              |
| **RoboFlamingo** | DeepMind    | Flamingo 기반            | VLM + robot control   |
| **Helix**        | Figure AI   | dual-system architecture | reasoning + motor     |
| **GR00T**        | NVIDIA      | robot foundation model   | large robotics model  |
| **MobileVLA**    | 연구        | edge-optimized VLA       | on-device inference   |
| **FUTURE-VLA**   | 연구        | predictive VLA           | trajectory prediction |
| **A2C2 VLA**     | 연구        | action chunk correction  | fast control          |

---

## 주요 구조 유형

현재 VLA는 **4가지 구조**로 분류됩니다.

### ① Robotics Transformer

```text
vision tokens
+
language tokens
        ↓
transformer
        ↓
action tokens
```

대표

- RT-1
- RT-2

특징

- end-to-end 학습
- 자연어 reasoning 강함

단점

- latency 큼

---

### ② Foundation Robot Model

```text
vision
+
language
+
robot state
        ↓
foundation model
        ↓
policy head
```

대표

- PaLM-E
- GR00T

특징

- 범용 로봇 모델
- 대규모 데이터

---

### ③ Dual-System VLA

```text
slow reasoning model
        ↓
latent task plan
        ↓
fast motor policy
```

대표

- Helix

특징

- reasoning과 control 분리
- 휴머노이드에 적합

---

### ④ Predictive VLA

```text
current state
        ↓
future trajectory prediction
        ↓
robot control
```

대표

- FUTURE-VLA

특징

- long-horizon task 처리

---

✔ 핵심

현재 연구 흐름

```text
end-to-end VLA
        ↓
hybrid VLA
        ↓
real-time VLA
```

---

# 2️⃣ VLA 시스템에서 실제 병목 연산 TOP 5

실제 로봇 시스템에서 **연산량 대부분은 몇 가지 연산에 집중**됩니다.

---

# ① Vision Encoder Attention

가장 큰 병목입니다.

예

```text
ViT-Large
≈ 60~100 GFLOPs / frame
```

로봇에서

```text
10 FPS → 1 TFLOPs
```

수준입니다.

---

# ② Multimodal Attention

VLA는 다음 토큰을 함께 처리합니다.

```text
vision tokens
language tokens
robot state
history
```

attention complexity

```text
O(n²)
```

토큰 수 증가 → 계산 폭증

---

# ③ KV Cache Update

LLM 기반 VLA는 KV cache를 계속 업데이트합니다.

문제

```text
memory bandwidth bottleneck
```

특히

```text
edge NPU
```

에서 심각합니다.

---

# ④ Vision Patch Embedding

이미지를 patch token으로 변환하는 과정

예

```text
224×224 image
→ 196 tokens
```

초기 convolution 연산이 많습니다.

---

# ⑤ Action Head Sampling

action token 생성 과정

예

```text
trajectory generation
inverse kinematics
```

특히 **multi-step action decoding**에서 계산량 증가합니다.

---

✔ 실제 연산 비율 (대략)

| 연산                 | 비율   |
| -------------------- | ------ |
| Vision encoder       | 60–70% |
| Multimodal attention | 20–25% |
| KV cache update      | 5–10%  |
| Action decoding      | 5–10%  |

---

# 3️⃣ 100ms 온디바이스 VLA 하드웨어 요구사항

100ms VLA를 구현하려면 **특정 수준 이상의 compute와 memory bandwidth**가 필요합니다.

---

# 최소 요구 GPU/NPU 성능

대략적인 기준

```text
30–50 TOPS AI compute
```

이 필요합니다.

---

# 대표 edge AI 플랫폼

## NVIDIA Jetson Orin

성능

```text
275 TOPS
```

현재 로봇 AI에서 가장 많이 사용됩니다.

---

## Qualcomm RB5 / RB6

모바일 로봇용 SoC

특징

```text
low power AI
```

---

## Intel Core Ultra + NPU

최근 PC/로봇용

---

## Custom Robotics NPU

예

```text
Tesla FSD chip
Huawei Ascend
```

---

# 메모리 요구사항

VLA 모델 실행에는

```text
16–32 GB memory
```

가 필요합니다.

---

# 메모리 대역폭

Transformer는 memory bandwidth 의존도가 높습니다.

권장

```text
> 100 GB/s bandwidth
```

---

# 전력 제약

휴머노이드 로봇에서는

```text
20–50 W AI compute
```

수준이 현실적입니다.

---

# 실제 로봇 AI compute 예

| 플랫폼        | AI compute |
| ------------- | ---------- |
| Jetson Orin   | 275 TOPS   |
| Jetson Xavier | 32 TOPS    |
| Tesla FSD     | ~144 TOPS  |
| Ascend 310    | 16–32 TOPS |

---

✔ 핵심

100ms 온디바이스 VLA는 보통

```text
50–200 TOPS
```

급 AI compute가 필요합니다.

---

# 최종 핵심 정리

현재 VLA 기술의 핵심 포인트는 다음 세 가지입니다.

```text
1️⃣ Vision encoder가 가장 큰 연산 병목
2️⃣ Hybrid VLA architecture가 현실적인 방향
3️⃣ 50~200 TOPS급 edge compute 필요
```

즉

> 온디바이스 VLA는 **AI 모델보다 시스템 설계와 하드웨어 최적화가 핵심 기술**입니다.
