# 정반식당 메뉴 → Slack 알림

네이버 지도 **정반식당** 피드에서 주간메뉴표를 가져와 Slack으로 자동 알림합니다.

| 스케줄 | 내용 |
|--------|------|
| 매주 월요일 09:30 | 주간메뉴표 **이미지** 전송 |
| 평일 매일 09:35 | Surya OCR로 추출한 **오늘의 메뉴 텍스트** 전송 |

## 요구 사항

- Node.js 18+
- Python 3.10+
- Slack Incoming Webhook URL

## 설치

```bash
npm install
pip install -r requirements.txt
```

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## 실행

```bash
# 월요일 — 이미지 전송
npm run fetch-menu

# 평일 — OCR 텍스트 전송
npm run fetch-menu-ocr
```

## CI/CD 스케줄 설정

**GitHub Actions** — `SLACK_WEBHOOK_URL` Secret 등록 후 자동 실행됩니다.

**GitLab CI** — Pipeline schedules에 아래 두 스케줄 추가:

| Cron | 변수 | 내용 |
|------|------|------|
| `30 0 * * 1` | `JOB_TYPE=image` | 월요일 이미지 |
| `35 0 * * 1-5` | `JOB_TYPE=ocr` | 평일 OCR 텍스트 |

## 디렉터리 구조

```
jeongban/
├── scripts/
│   ├── fetch-menu-and-notify.js     # 이미지 전송 진입점
│   └── fetch-menu-ocr-and-notify.js # OCR 텍스트 전송 진입점
│   └── ocr-menu.py                  # Surya OCR 파이프라인
├── src/
│   ├── naver-feed.js                # 네이버 피드 크롤링
│   └── slack-notify.js              # Slack Webhook 전송
├── .github/workflows/fetch-menu.yml
├── .gitlab-ci.yml
└── requirements.txt
```

## 주의사항

- 네이버 자동 수집은 개인/내부 알림 용도로만 사용하세요.
- 네이버 페이지 구조 변경 시 `src/naver-feed.js` 셀렉터를 확인하세요.
- OCR 실패 또는 공휴일 감지 시 Slack 전송을 생략합니다.
