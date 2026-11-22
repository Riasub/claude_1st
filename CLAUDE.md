# claude_1st - 네이버 블로그 카페·음식점 후기 초안 도구

사용자가 직접 다녀온 카페·음식점의 방문 기록(`visit.yaml`)과 사진으로 네이버 블로그 후기 초안을 만든다.
발행은 사용자가 직접 한다. 네이버 블로그에 자동으로 로그인하거나 글을 올리는 코드(브라우저 자동화, 매크로)는 만들지 않는다.

## 구조
- `blogdraft/visit.py` 방문 기록 읽기 (빈 칸은 `prune`으로 제거)
- `blogdraft/photos.py` 사진 정리: 회전 보정, 1600px로 축소, EXIF(GPS 포함) 제거, 순서 정하기
- `blogdraft/naver.py` 네이버 지역 검색 API (선택, `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`)
- `blogdraft/writer.py` 지시문(`RULES` + `style.md`), Claude API 호출, 결과 정리(`normalize_post`)
- `blogdraft/render.py` `post.txt` / `tags.txt` / `preview.html` 생성, 협찬 표시, 가게 정보 칸
- 테스트: `python -m pytest -q`

## 클라우드 세션에서 초안 쓰기 (API 키 없이)
사용자가 "이 방문 초안 써줘"처럼 요청하면:
1. `python -m blogdraft build <방문 폴더> --no-ai` 실행 -> `draft/prompt.md`, `draft/photos/NN.jpg` 생성
2. `draft/prompt.md`를 읽고, 거기 나온 사진 파일을 모두 열어 본다.
3. `prompt.md`의 규칙과 스키마대로 `draft/post.json`을 쓴다. 기록에 없는 사실은 지어내지 않고, 추측한 부분은 `check`에 넣는다.
4. `python -m blogdraft render <방문 폴더>` 실행 후 결과(`draft/preview.html`)를 사용자에게 보여 준다.

## 주의
- `visits/`는 개인 사진과 기록이라 `.gitignore`에 들어 있다. 이 저장소는 공개 저장소이므로 사용자가 명시적으로 원할 때만 커밋한다.
- 비밀 값은 `.env`(로컬) 또는 클라우드 환경의 네트워크 시크릿에만 둔다. 코드나 커밋에 넣지 않는다.
