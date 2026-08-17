# 📖 PTZ Preset Auto Set 설치 및 운용 가이드 (Installation & Operator Guide)

본 문서는 교회 및 방송실 환경에서 **PTZ 카메라 자동 미세 보정 시스템(PTZ Preset Auto Set)**을 설치하고, 카메라 네트워크 및 AI 구도를 세팅하여 운용하는 전체 절차를 안내합니다.

---

## 📋 1. 권장 시스템 사양 및 환경 요구사항

- **운영체제**: Windows 10 / 11 (64-bit) 또는 Linux
- **Python 버전**: Python 3.10 이상 (Python 3.12 지원)
- **네트워크**: 교회 방송실 전용 LAN 네트워크 (PTZ 카메라 7대 및 서버 PC 수평 연결)
- **카메라 장비 사양**:
  - VISCA over IP (UDP 또는 TCP 포트 default: `52381`) 지원 PTZ 카메라 (예: ST20, Birddog, Sony 등)
  - H.264 / H.265 RTSP 스트림 지원 (`rtsp://<IP>:554/stream1`)
- **하드웨어 제어기**: Elgato Stream Deck XL / 32키 (선택 사항)

---

## 🚀 2. 프로그램 설치 절차 (Step-by-Step)

### Step 1: 소스코드 준비
터미널(PowerShell 또는 Command Prompt)을 열고 작업 디렉토리로 이동합니다.

```powershell
cd C:\workspace\PTZ-Preset-Auto-Set
```

### Step 2: Python 가상환경 생성 및 활성화 (권장)
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### Step 3: 필수 의존성 패키지 설치
`requirements.txt`에 명시된 FastAPI, OpenCV, ONNX Runtime, Tau-J/rtmlib 패키지를 설치합니다.

```powershell
pip install -r requirements.txt
```

---

## 💻 3. 시스템 서버 실행 및 접속

### 서버 구동 명령
```powershell
python -m app.main
```
*(성공 시 `INFO: Uvicorn running on http://0.0.0.0:8000` 라이브 메시지가 출력됩니다.)*

### 웹 관리자 UI 접속
웹 브라우저(Chrome / Edge 권장)를 열고 다음 주소로 접속합니다.
- **메인 대시보드**: `http://localhost:8000`
- **카메라 장비 관리**: `http://localhost:8000/cameras`

---

## ⚙️ 4. 초기 세팅 및 현장 설치 절차

### 1단계: 카메라 네트워크 및 연결 등록 (`/cameras`)
1. 상단 메뉴 **[카메라 관리]** (`http://localhost:8000/cameras`)로 이동합니다.
2. 각 카메라 카드에서 **`[설정 수정]`** 버튼을 클릭하거나 상단 **`[+ 카메라 신규 추가]`**를 누릅니다.
3. 카메라 정보 입력:
   - **카메라 명칭**: 예) `CAM 1 (설교자 전용)`, `CAM 2 (찬양팀)`
   - **IP Address**: 카메라 IP (예: `192.168.1.101`)
   - **VISCA Port / Protocol**: `52381` / `UDP` (또는 TCP)
   - **RTSP Stream URL**: `rtsp://192.168.1.101:554/stream1`
   - **RTSP 계정**: Username 및 Password (필요시 입력)
4. **`[저장 전 연결 테스트]`** 버튼을 눌러 **PTZ (VISCA) 🟢 CONNECTED** 및 **VIDEO (RTSP) 🟢 STREAMING** 2단계 통신 상태를 확인한 후 저장합니다.

---

### 2단계: 프리셋 생성 및 BASE/LIVE 매핑 (`/cameras/{id}/presets`)
1. 카메라 카드의 **`[🎯 프리셋 관리]`** 버튼을 클릭합니다.
2. **`[+ 프리셋 신규 추가]`** 버튼을 눌러 보정할 프리셋을 생성합니다:
   - **BASE Preset 번호**: 사람(엔지니어)이 카메라로 직접 맞춘 원본 보존 프리셋 번호 (예: `1`)
   - **LIVE Preset 번호**: 예배 전 AI가 자동 보정한 결과를 저장할 프리셋 번호 (예: `101`)
   - **Target Mode**:
     - `SINGLE`: 1인 설교자/목회자 단독 Close-up
     - `GROUP`: 2인/3인/4인 찬양팀 그룹 Framing
   - **Vertical Metric (Headroom)**: `EYE_Y` (눈높이) 또는 `GROUP_TOP` (그룹 상단 머리 위 여백)
3. **`[저장]`**을 클릭합니다.

> ⚠️ **중요 (BASE 원본 보호 정책)**: BASE Preset 번호와 LIVE Preset 번호는 서로 다르게 지정해야 합니다. 시스템의 하드 가드(Hard Guard)가 작동하여 BASE Preset 번호에는 절대로 자동 보정 결과가 덮어씌워지지 않습니다.

---

### 3단계: 마우스 기반 ROI 및 Target 구도 설정 (`/roi-editor/{preset_id}`)
1. 프리셋 목록의 **`[⚙️ ROI 구도 설정]`** 버튼을 클릭합니다.
2. 실시간 카메라 가이드 화면이 나타납니다:
   - **마우스 드래그**: 인물 감지 ROI 영역 (녹색 상자)을 지정합니다. (무대 바깥 배경이나 화면 밖 노이즈 감지 차단)
   - **마우스 클릭**: 방송 화면상 인물의 목표 배치 위치 (빨간색 십자가 Target X, Y)를 지정합니다.
3. 우측 상단 **`[설정 저장]`** 버튼을 누릅니다.

---

## 🎬 5. 실시간 예배 전 운용 방법 (`/`)

1. 메인 대시보드 (`http://localhost:8000`)로 이동합니다.
2. 예배 시작 5~10분 전 무대에 인물(설교자/찬양팀)이 입장하면 상단 **`[AUTO SET ALL]`** 버튼을 누릅니다.
3. AI 엔진이 각 카메라별로 RTSP 영상 프레임을 분석하여 지정된 Target 구도로 PTZ Pan/Tilt를 미세 조정한 뒤 **LIVE Preset 번호**에 자동 저장합니다.
4. 실패한 프리셋이 발생한 경우 **`[RETRY FAILED]`** 버튼을 눌러 해당 프리셋만 선별 재시도할 수 있습니다.

---

## 🕹️ 6. Stream Deck 32키 연동 방법

본 시스템은 Elgato Stream Deck 32키 장치와 완벽하게 연동됩니다.

1. Stream Deck 앱을 실행합니다.
2. `streamdeck_plugin/` 폴더를 플러그인 디렉토리에 등록합니다.
3. 버튼 배치 구성:
   - **Row 1~3 (키 1~24)**: 개별 프리셋 원클릭 AutoSet 버튼
   - **Row 4 Col 1**: `[PREV PAGE]`
   - **Row 4 Col 2**: `[AUTO SET ALL]`
   - **Row 4 Col 3**: `[RETRY FAILED]`
   - **Row 4 Col 4**: `[RESET STATUS]`
   - **Row 4 Col 5**: `[CANCEL]`
   - **Row 4 Col 8**: `[NEXT PAGE]`

---

## 🛠️ 7. 트러블슈팅 (Troubleshooting)

| 현상 | 원인 | 조치 방법 |
| :--- | :--- | :--- |
| **PTZ (VISCA) FAILED** | 카메라 IP가 틀렸거나 VISCA 포트(52381) 방화벽 차단 | 카메라 IP ping 테스트 및 `52381` 포트 통신 상태 확인 |
| **VIDEO (RTSP) FAILED** | RTSP URL 주소 오류 또는 비밀번호 틀림 | `rtsp://<IP>:554/stream1` 계정 및 비밀번호 재확인 |
| **`no such column` DB 에러** | 기존 DB 스키마 미갱신 | 서버 재시도시 자동 마이그레이션이 실행되며, 해결 안될 시 `data/autoset.db` 삭제 후 재시작 |
| **Preset Save Blocked 에러** | BASE Preset 번호에 저장 시도 | BASE 번호와 LIVE 번호가 다르게 매핑되었는지 확인 |
