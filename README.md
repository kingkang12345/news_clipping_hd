<<<<<<< HEAD
# PwC 뉴스 분석기

회계법인 관점에서 중요한 뉴스를 자동으로 분석하는 AI 도구입니다.

## 기능
- Google News에서 실시간 뉴스 수집
- GPT를 활용한 뉴스 분석
- 회계법인 관점의 중요 뉴스 선별
- 분석 결과 워드 문서 출력

## 설치 및 실행
1. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

2. 환경 변수 설정:
- `.env` 파일을 생성하고 필요한 API 키 설정
- 또는 Streamlit Cloud의 secrets 관리 기능 사용

3. 실행:
```bash
streamlit run app.py
```
```

4. GitHub에 코드 push:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin [GitHub 저장소 URL]
git push -u origin main
```

5. Streamlit Cloud 배포:
   1. https://share.streamlit.io/ 접속
   2. GitHub 계정 연동
   3. 저장소 선택
   4. Deploy 클릭

6. Streamlit Cloud에서 환경 변수 설정:
   - Settings > Secrets에서 환경 변수 추가:
   ```toml
   OPENAI_API_KEY = "your-api-key"
   ```
=======
# news_clipping
>>>>>>> a3f9e7eb0d697e2388753a728b62cc5c1f8721f6
