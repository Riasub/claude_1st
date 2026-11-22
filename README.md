# claude_1st

카페·음식점 방문 기록과 사진으로 **네이버 블로그 후기 초안**을 만드는 도구입니다.

- 사진 정리: 회전 보정, 블로그용 크기 조정, **GPS 위치 등 메타데이터 제거**, `01.jpg`, `02.jpg` … 순서대로 저장
- 가게 정보: 네이버 지역 검색으로 주소·전화번호 자동 채우기 (선택)
- 초안 작성: Claude가 내 기록과 사진만 근거로 제목·본문·태그 작성, 추측한 부분은 "확인할 점"으로 표시
- 결과: 미리보기(`preview.html`)에서 **제목 / 본문 / 태그 복사** 버튼으로 블로그 에디터에 붙여 넣기
- 협찬 글이면 글 맨 위에 표시 문구 자동 삽입

> 네이버는 2020년에 블로그 글쓰기 API를 종료했습니다. 이 도구는 발행 직전까지만 자동화하고,
> 발행(또는 예약 발행)은 직접 합니다. 계정 정지 위험이 있는 로그인·자동 게시는 하지 않습니다.

## 설치 (내 PC, 처음 한 번)

Python 3.10 이상이 필요합니다.

```bash
git clone https://github.com/Riasub/claude_1st.git
```

```bash
cd claude_1st
```

```bash
pip install -r requirements.txt
```

`.env.example`을 `.env`로 복사한 뒤 키를 적습니다.
- `ANTHROPIC_API_KEY`: [Claude 콘솔](https://platform.claude.com)에서 발급. 없으면 AI 초안 없이 사진 정리와 작성 요청서만 만듭니다.
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: [네이버 개발자센터](https://developers.naver.com/apps)에서 애플리케이션 등록 후 **검색** API 선택. 없으면 가게 정보 검색만 건너뜁니다.

## 사용법

**1. 방문 폴더 만들기**

```bash
python -m blogdraft new "카페 온새"
```

`visits/2026-11-22-카페-온새/` 폴더가 생깁니다.

**2. 사진과 기록 넣기**
- `photos/` 폴더에 사진을 넣습니다. (아이폰 HEIC는 JPG로 내보내서 넣어 주세요)
- `visit.yaml`에 메뉴, 가격, 느낀 점을 적습니다. 직접 경험한 것만 적으면 그것만 글에 들어갑니다.

**3. 초안 만들기**

```bash
python -m blogdraft build "visits/2026-11-22-카페-온새"
```

**4. 확인하고 붙여 넣기**
- `draft/preview.html`을 브라우저로 열어 내용을 확인합니다. 노란 상자의 "확인할 점"을 꼭 봐 주세요.
- 복사 버튼으로 제목, 본문, 태그를 블로그 에디터에 붙여 넣습니다.
- 본문의 `[사진 3]` 자리에 `draft/photos/03.jpg`를 올립니다.

### 그 밖의 옵션
- 초안을 손으로 고쳤다면: `draft/post.json` 수정 후 `python -m blogdraft render <방문 폴더>`
- 비용 절약: `--no-images` (사진을 Claude에게 보내지 않음)
- 네이버가 다른 가게를 찾았다면: `visit.yaml`의 `search_query`를 고치고 `--refresh-place`
- 말투와 글 구성 바꾸기: `style.md` 수정
- 모델 바꾸기: `.env`에 `BLOG_MODEL`, `BLOG_EFFORT`

## Claude 앱 채팅으로 쓰기 (가장 간단)

1. 갤러리에서 사진을 고르고 공유 → **Claude** (또는 채팅에 직접 첨부)
2. 가게 이름, 메뉴·가격, 느낀 점을 몇 줄 적고 **"후기 초안 써줘"**
3. 채팅에 제목·본문·태그가 복사하기 좋게 나오고, 노션 "블로그 후기" 데이터베이스에도 기록됩니다.
4. 네이버 블로그에 붙여 넣고, `[사진 N]` 자리에 N번째로 보낸 사진을 넣어 발행합니다.

API 키가 필요 없습니다. 처리 순서는 `CLAUDE.md`에 적혀 있습니다.

⚠️ 이 저장소는 **공개 저장소**입니다. `visits/` 폴더(사진, 기록)는 git에 올라가지 않도록 막혀 있습니다.
