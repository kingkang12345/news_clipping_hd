from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
from dotenv import load_dotenv
from news_ai import collect_news, filter_news, AgentState

# 환경 변수 로드
load_dotenv()

app = FastAPI(title="PwC News Analysis API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class NewsAnalysisRequest(BaseModel):
    keyword: str
    analysis_prompt: Optional[str] = None

class NewsItem(BaseModel):
    content: str
    url: str
    date: Optional[str] = None

class NewsAnalysisResponse(BaseModel):
    news_data: List[NewsItem]
    filtered_news: List[NewsItem]
    analysis: str
    keyword: str

@app.get("/")
async def root():
    return {"message": "Welcome to PwC News Analysis API"}

@app.post("/analyze", response_model=NewsAnalysisResponse)
async def analyze_news(request: NewsAnalysisRequest):
    try:
        # 초기 상태 설정
        initial_state = {
            "news_data": [], 
            "filtered_news": [], 
            "analysis": "", 
            "keyword": request.keyword,
            "prompt": request.analysis_prompt
        }
        
        # 뉴스 수집
        state_after_collection = collect_news(initial_state)
        
        # 뉴스 필터링 및 분석
        final_state = filter_news(state_after_collection)
        
        return NewsAnalysisResponse(**final_state)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
