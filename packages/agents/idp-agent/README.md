# IDP Agent

## 로컬 실행 방법

```bash
# 1. 의존성 설치
uv sync

# 2. 가상환경 활성화
source .venv/bin/activate

# 3. 서버 실행
python -m main
```

서버가 `http://localhost:8080`에서 실행됩니다.

## 테스트 요청

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: test-session" \
  -d '{"prompt": "1 + 2는 뭐야?", "session_id": "test-123"}'
```
