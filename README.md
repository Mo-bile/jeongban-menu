# 정반식당 주간 메뉴 → Slack 알림

네이버 지도 **고메드갤러리아 큰길타워 정반식당** place 피드에서 매주 최신 주간메뉴표(첫 번째 글)를 수집해 Slack으로 알림을 보내는 자동화입니다.

## 요구 사항

- Node.js 18+
- Slack Incoming Webhook URL

## 설치

```bash
npm install
```

`npm install` 시 Playwright Chromium이 자동 설치됩니다 (`postinstall` 스크립트).

## Slack Webhook 발급

1. [Slack API](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. 앱 이름과 워크스페이스 선택 후 생성
3. **Incoming Webhooks** → **Activate Incoming Webhooks** 켜기
4. **Add New Webhook to Workspace** → 알림을 받을 채널 선택
5. 생성된 **Webhook URL**을 복사해 `.env`에 사용합니다.

## 설정

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

**.env 예시:**

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00.../B00.../xxx...
```

선택 사항:

- `PLACE_URL` — 기본값은 정반식당 피드 URL입니다. 다른 place 피드를 쓰려면 변경하세요.

## 실행

```bash
npm run fetch-menu
```

또는:

```bash
SLACK_WEBHOOK_URL=your_url node scripts/fetch-menu-and-notify.js
```

## 매주 자동 실행 (cron)

로컬/서버에서 매주 특정 요일·시간에 실행하려면 cron을 사용합니다.

예: 매주 월요일 오전 9시

```bash
crontab -e
```

추가:

```
0 9 * * 1 cd /Users/mojaeyeong/Documents/ownProject/jeongban && /usr/local/bin/node scripts/fetch-menu-and-notify.js
```

`node` 경로는 `which node`로 확인한 뒤 넣으세요. `.env`는 프로젝트 루트에 두면 스크립트가 자동으로 로드합니다.

## GitHub Actions에서 매주 실행

1. 이 저장소를 GitHub에 푸시
2. **Settings** → **Secrets and variables** → **Actions** 에서 `SLACK_WEBHOOK_URL` 추가
3. `.github/workflows/fetch-menu.yml` 생성 예시:

```yaml
name: Weekly menu notification
on:
  schedule:
    - cron: '0 0 * * 1'   # 매주 월요일 00:00 UTC (한국 09:00)
  workflow_dispatch:
jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npx playwright install chromium --with-deps
      - run: node scripts/fetch-menu-and-notify.js
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## GitLab CI/CD에서 매주 실행

GitLab에는 "Actions" 대신 **CI/CD 파이프라인**이 있습니다. 같은 스크립트를 매주 돌리려면:

1. 이 저장소를 GitLab에 푸시
2. **Settings** → **CI/CD** → **Variables** 에서 변수 추가:
   - Key: `SLACK_WEBHOOK_URL`
   - Value: `https://hooks.slack.com/services/...` (Webhook URL)
   - **Mask variable** 체크 (선택, 보안 권장)
3. **Settings** → **CI/CD** → **Pipeline schedules** 에서 스케줄 추가:
   - 예: 매주 월요일 09:00 (한국 시간에 맞게 Cron 식 입력)

수동 실행은 **Run pipeline** → **Run pipeline** 으로 하면 됩니다.  
설정은 `.gitlab-ci.yml`에 있으며, Playwright 공식 Docker 이미지를 사용합니다.

## 주의사항

- **네이버 이용약관**: 자동 수집은 개인/내부 알림 용도로만 사용하고, 요청 빈도를 낮게 유지하세요.
- **HTML 구조 변경**: 네이버가 페이지 구조를 바꾸면 셀렉터가 깨질 수 있습니다. 실패 시 `src/naver-feed.js`의 셀렉터를 확인해 수정하세요.
- **이미지 URL**: 네이버 이미지 링크가 일부 환경에서 Slack에서 바로 안 뜰 수 있습니다. 필요하면 이미지 블록을 제거하거나 대체 텍스트만 사용할 수 있습니다.

## 디렉터리 구조

```
jeongban/
├── package.json
├── .env.example
├── .gitlab-ci.yml                 # GitLab CI/CD (매주/수동 실행)
├── .github/workflows/
│   └── fetch-menu.yml             # GitHub Actions (매주/수동 실행)
├── scripts/
│   └── fetch-menu-and-notify.js   # 진입점
├── src/
│   ├── naver-feed.js              # Playwright로 첫 피드 항목 파싱
│   └── slack-notify.js            # Slack Webhook 전송
└── README.md
```
