# PTZ Preset Auto Set System

교회 방송실 환경을 위한 **AI 기반 PTZ 카메라 프리셋 자동 보정 및 안전 보존 시스템**입니다.

---

## 🌟 핵심 컨셉 (Dual Preset Concept)

1. **BASE Preset (원본 보존 / Read-Only)**
   - 사람이 직접 맞춰둔 이상적인 프리셋.
   - 시스템 내 `ProtectedPTZController` 하드 가드에 의해 WRITE 명령이 원천 차단됩니다.
2. **LIVE Preset (예배 전 자동 보정 / Write Target)**
   - 예배 시작 전 설교자 및 찬양팀의 실제 키/위치에 맞춰 AI Closed-Loop 미세 보정 후 저장되는 프리셋.

---

## 🚀 주요 기능

- **SINGLE & GROUP Target Mode**
  - **SINGLE Mode**: 1인 Close/Medium Shot Target Lock 유지
  - **GROUP Mode**: 2인/3인/4인 찬양팀 Virtual Group Bounding Box 구도 및 Headroom (`vertical_metric`) 보정
- **Vision Engine**: `Tau-J/rtmlib` + `RTMPose` + `ONNX Runtime`
- **Stream Deck 연동**: 32키 Stream Deck 연동 REST/WebSocket 엔드포인트 지원
- **안전 장치**: BASE Preset 저장 차단 하드 가드, Motion Limit Guard, Multi-frame Target Stabilizer

---

## 🛠️ 설치 및 실행 방법

### 1. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 서버 실행

```bash
python -m app.main
```

실행 후 웹 브라우저에서 대시보드 접속:
`http://localhost:8000` (또는 교회 방송 네트워크 IP `http://192.168.x.x:8000`)

---

## ⚙️ Windows 부팅 시 자동 실행 설정 (Task Scheduler)

방송 PC 전원이 켜지면 수동 조작 없이 서버가 자동으로 시작되도록 설정합니다.

1. `Win + R` → `taskschd.msc` 실행 (작업 스케줄러)
2. **작업 만들기...** 클릭
3. 일반 탭: `사용자가 로그온할 때만 실행` 및 `가장 높은 권한으로 실행` 체크
4. 트리거 탭: **새로 만들기** → `시스템 시작 시` 또는 `로그온 할 때` 선택
5. 동작 탭: **새로 만들기** → `프로그램 시작`
   - 프로그램/스크립트: `python.exe` 경로 (예: `C:\Python312\python.exe`)
   - 인수 추가: `-m app.main`
   - 시작 위치: `C:\workspace\PTZ-Preset-Auto-Set`
6. 저장 후 확인.

---

## 📄 AI 모델 & 라이선스

- **Tau-J/rtmlib**: MIT License
- **RTMPose / ONNX Runtime**: Apache-2.0 License
