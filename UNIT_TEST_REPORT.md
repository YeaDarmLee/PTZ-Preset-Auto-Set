# PTZ Preset Auto Set System - Unit Test & Feature Report

본 보고서는 **PTZ Preset Auto Set 시스템**의 **동적 Auto Set 설정 튜닝 엔진 (`/settings/auto-set`)**, **3단계 필드 수준 상속 (Field-Level Merge)**, **2단계 Dry Run 엔진**, **Safety Hard Clamp 안전 장치** 구현 및 단위 테스트 검증 결과입니다.

---

## 📋 1. 개요 및 구현 기능 요약

1. **Auto Set 설정 페이지 (`/settings/auto-set`) 웹 UI**:
   - 방송실 운영자가 코드 수정 없이 웹 브라우저에서 Pan/Tilt Gain, Dead Zone(%), PTZ 속도, Safety Limit, Tolerance, AI Confidence threshold를 조절 가능.
2. **3단계 필드 수준 상속 (3-Tier Field-Level Merge)**:
   - `PRESET` Override $\rightarrow$ `CAMERA` Override $\rightarrow$ `GLOBAL` Default $\rightarrow$ `System Fallback`
   - `NULL` 필드 단위 수직 상속 해소 및 Effective Preview (값, 출처 뱃지, System Hard Limit) 제공.
3. **Safety Hard Clamp & Correction vs. Speed 분리**:
   - `Error × Gain` = `Raw Correction Delta` (위치 보정 이동 수치)
   - `pan_speed` / `tilt_speed` = PTZ 모터 실행 속도 (VISCA 1~24, 1~20)
   - DB/UI에서 큰 `max_pan_limit = 999.0`을 입력하더라도 `SYSTEM_HARD_MAX_PAN_DELTA(15.0)` 이하로 2중 클램프.
4. **Tolerance Pre-check & STALLED 조기 종료**:
   - Target Tolerance 성공 판정을 PTZ 보정 계산보다 먼저 수행.
   - Tolerance 미충족이나 Dead Zone / Min Correction으로 인해 Pan/Tilt Delta가 모두 0이 된 경우 무한 루프 없이 `STALLED` 상태로 즉시 조기 종료.
5. **2단계 Dry Run 지원**:
   - **Calculation Test**: RTSP/AI 미사용 pure math 오차 및 보정 수치 시뮬레이션.
   - **Live Dry Run**: RTSP 프레임 + AI 분석 수행 (PTZ Move ❌, Preset Recall/Save 100% 스킵).

---

## 📁 2. 테스트 디렉터리 및 모듈 구조

```text
PTZ-Preset-Auto-Set/
├── pytest.ini                     # Pytest 옵션 및 unit/integration 마커 설정
├── tests/
│   ├── conftest.py                # In-Memory SQLite DB (PRAGMA foreign_keys=ON) 및 Pytest Fixture
│   ├── test_visca_guard.py        # PTZ Guard 하드 가드 테스트
│   └── unit/                      
│       ├── test_preset_service.py   # BASE Preset 원본 보호 (Hard Guard) 검증
│       ├── test_auto_set_service.py # AutoSet Closed-Loop 파이프라인 전 과정 테스트
│       ├── test_motion_controller.py# PTZ P-Control 보정량/속도 및 Safety Limit 검증
│       ├── test_roi_service.py      # ROI 좌표계 Normalization & Target 계산
│       ├── test_camera_health.py    # VISCA & RTSP 분리 진단 및 상호 독립성 검증
│       ├── test_retry_service.py    # FAILED 항목 선별 재시도 테스트
│       ├── test_vision_mock.py      # AI Target/Group 선택 및 Virtual BBox 계산
│       ├── test_exceptions.py       # 예외 및 타임아웃 안강성(Robustness) 테스트
│       └── test_settings_service.py # 💡 신규: 3-Tier Merge, Safety Clamp, STALLED Exit, Dry Run 단위 테스트
```

---

## 🛡️ 3. 신규 추가된 단위 테스트 검증 항목 (`test_settings_service.py`)

1. **`test_field_level_merge_and_overrides`**:
   Global (`pan_gain=18.0`, `tilt_gain=14.0`), Camera 1 (`pan_gain=14.0`), Preset 1 (`deadzone_x=0.02`) 설정 시 `pan_gain=14.0` (Camera), `tilt_gain=14.0` (Global), `deadzone_x=0.02` (Preset) 수직 상속 해소 검증.
2. **`test_override_deletion_and_fallback`**:
   Preset Override 삭제 시 Camera/Global 상속 복귀, Camera Override 삭제 시 Global 상속 복귀 검증.
3. **`test_preset_camera_hierarchy_validation`**:
   타 카메라 소속 Preset ID로 Override 저장 시 `ValueError` 거부 검증.
4. **`test_tolerance_smaller_than_deadzone_rejected`**:
   `tolerance_x < deadzone_x` 설정 시 무한 수렴 루프 방지를 위한 `ValueError` 거부 검증.
5. **`test_axis_independent_deadzone_4_combinations`**:
   X/Y 4가지 Dead Zone 조합(X IN / Y OUT, X OUT / Y IN, X IN / Y IN, X OUT / Y OUT)에 대한 축별 독립 보정 검증.
6. **`test_system_hard_clamp_enforcement`**:
   DB soft limit = 999.0 입력 시에도 `SYSTEM_HARD_MAX_PAN_DELTA(15.0)` 이하로 2중 안전 클램핑 검증.
7. **`test_calculation_test_pure_math`**:
   Zero RTSP/AI/PTZ 상태에서 pure math 계산 결과 산출 검증.
8. **`test_live_dry_run_skips_ptz_and_preset_save`**:
   Live Dry Run 실행 시 PTZ Move ❌, Preset Recall ❌, Preset Save 모듈의 `assert_not_called()` 검증.
9. **`test_tolerance_pre_check_avoids_extra_movement`**:
   Iteration 1차에서 Tolerance 만족 시 PTZ 이동(move_relative) 없이 즉시 SUCCESS 종료 검증.
10. **`test_stalled_early_termination`**:
    Tolerance 미충족 & PTZ Delta = 0 상태 시 STALLED 조기 종료 검증.
