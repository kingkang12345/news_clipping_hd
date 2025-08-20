#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Web Scraper for News Articles
-----------------------------
뉴스 기사 URL에서 본문을 추출하는 웹 스크래핑 모듈입니다.
"""

import requests
from bs4 import BeautifulSoup
import time
from typing import Optional, Dict, List, Tuple
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from enum import Enum
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Google News URL 디코더 (선택적)
try:
    from googlenewsdecoder import gnewsdecoder
    GOOGLE_NEWS_DECODER_AVAILABLE = True
except ImportError:
    GOOGLE_NEWS_DECODER_AVAILABLE = False
    print("googlenewsdecoder가 설치되지 않았습니다. pip install googlenewsdecoder로 설치하세요.")

# newspaper3k 임포트 (선택적)
try:
    from newspaper import Article
    NEWSPAPER3K_AVAILABLE = True
except ImportError:
    NEWSPAPER3K_AVAILABLE = False
    print("newspaper3k가 설치되지 않았습니다. pip install newspaper3k로 설치하세요.")

# OpenAI API 임포트 (선택적)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("OpenAI API가 설치되지 않았습니다. pip install openai로 설치하세요.")


class ExtractionMethod(Enum):
    """추출 방법 열거형"""
    NEWSPAPER3K = "newspaper3k"
    CUSTOM_PARSER = "custom_parser"
    SELENIUM = "selenium"
    AI_FALLBACK = "ai_fallback"
    FAILED = "failed"


class ExtractionResult:
    """추출 결과 클래스"""
    def __init__(self, title: str = "", content: str = "", url: str = "", domain: str = "", 
                 method: ExtractionMethod = ExtractionMethod.FAILED, success: bool = False, 
                 error_message: str = "", extraction_time: float = 0.0):
        self.title = title
        self.content = content
        self.url = url
        self.domain = domain
        self.method = method
        self.success = success
        self.error_message = error_message
        self.extraction_time = extraction_time
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'title': self.title,
            'content': self.content,
            'url': self.url,
            'domain': self.domain,
            'method': self.method.value,
            'success': self.success,
            'error_message': self.error_message,
            'extraction_time': self.extraction_time
        }


class HybridNewsWebScraper:
    """
    하이브리드 뉴스 기사 웹 스크래핑 클래스
    1차: newspaper3k 범용 라이브러리
    2차: 커스텀 파서 (언론사별 특화)
    3차: 고급 Selenium (JavaScript 렌더링 사이트)
    4차: AI API 활용
    """
    
    def __init__(self, openai_api_key: Optional[str] = None, enable_ai_fallback: bool = True):
        """웹 스크래퍼 초기화"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # AI 설정
        self.enable_ai_fallback = enable_ai_fallback and OPENAI_AVAILABLE
        self.openai_client = None
        
        # Selenium 설정 (필요시 동적으로 생성)
        print("🔧 Selenium은 필요시 동적으로 초기화됩니다.")
        
        if OPENAI_AVAILABLE:
            try:
                # 환경변수에서 API 키 가져오기 (우선순위)
                import os
                api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
                
                if api_key:
                    # 최신 OpenAI 라이브러리 방식
                    try:
                        from openai import OpenAI
                        self.openai_client = OpenAI(
                            api_key=api_key,
                            base_url=os.getenv('OPENAI_BASE_URL')  # PwC 설정 지원
                        )
                        print("✅ OpenAI API 클라이언트 초기화 성공")
                    except Exception as init_error:
                        print(f"⚠️ OpenAI 클라이언트 초기화 실패: {init_error}")
                        self.enable_ai_fallback = False
                else:
                    self.enable_ai_fallback = False
                    print("⚠️ OpenAI API 키가 설정되지 않아 AI 폴백을 비활성화합니다.")
            except Exception as e:
                self.enable_ai_fallback = False
                print(f"⚠️ OpenAI API 초기화 실패: {e}")
        
        # 통계 추적
        self.stats = {
            ExtractionMethod.NEWSPAPER3K.value: {'success': 0, 'total': 0},
            ExtractionMethod.CUSTOM_PARSER.value: {'success': 0, 'total': 0},
            ExtractionMethod.AI_FALLBACK.value: {'success': 0, 'total': 0},
            ExtractionMethod.SELENIUM.value: {'success': 0, 'total': 0},
            'total_extractions': 0,
            'total_successes': 0
        }
        
        # 언론사별 커스텀 파서 설정 (개선된 버전)
        self.content_selectors = {
            # 한국 언론사 (우선순위별 선택자)
            'chosun.com': {
                'content': ['div.article-body', 'div.news_text', '.article_view', 'div.par'],
                'title': ['h1.headline', 'h1', '.article-title', 'title']
            },
            'biz.chosun.com': {
                'content': ['div.article-body', 'div.news_text', '.article_view', 'div.par', 'div.article_txt', '.story_content'],
                'title': ['h1.headline', 'h1', '.article-title', '.news_title', 'title']
            },
            'joongang.co.kr': {
                'content': ['div.article_body', 'div.article-body', '.article_content', 'div.article_content'],
                'title': ['h1.headline', 'h1', '.article-title']
            },
            'donga.com': {
                'content': ['div.article_txt', 'div.article-body', 'div.article_content'],
                'title': ['h1.title', 'h1', '.article-title']
            },
            'mk.co.kr': {
                'content': ['div.art_txt', 'div.news_cnt_detail_wrap', 'div.news_content'],
                'title': ['h1.news_ttl', 'h1', '.news-title']
            },
            'hankyung.com': {
                'content': ['div.article-body', 'div.news-content', 'div.article_txt'],
                'title': ['h1.headline', 'h1', '.article-title']
            },
            'fnnews.com': {
                'content': ['div.article-body', 'div.article_content', 'div.news_content'],
                'title': ['h1.article-headline', 'h1', '.article-title']
            },
            'mt.co.kr': {
                'content': ['div.article-body', 'div.news_text', 'div.news_content'],
                'title': ['h1.subject', 'h1', '.news-title']
            },
            'edaily.co.kr': {
                'content': ['div.news_body', 'div.article-body', 'div.news_content'],
                'title': ['h1.news_title', 'h1', '.article-title']
            },
            'asiae.co.kr': {
                'content': ['div.article-body', 'div.view_con', 'div.article_content'],
                'title': ['h1.article_title', 'h1', '.article-title']
            },
            'newsis.com': {
                'content': ['div.article-body', 'div.article_content', 'div.news_content'],
                'title': ['h1.article_title', 'h1', '.article-title']
            },
            'yonhapnews.co.kr': {
                'content': ['div.article-body', 'div.article_text', 'div.story-body'],
                'title': ['h1.tit', 'h1', '.article-title']
            },
            
            # 해외 언론사
            'reuters.com': {
                'content': ['div.ArticleBodyWrapper', 'div.StandardArticleBody_body', 'div.ArticleBody'],
                'title': ['h1[data-testid="Headline"]', 'h1', '.ArticleHeader_headline']
            },
            'bloomberg.com': {
                'content': ['div.body-content', 'div.article-body', 'div[data-module="ArticleBody"]'],
                'title': ['h1[data-module="ArticleHeader"]', 'h1', '.headline']
            },
            'yahoo.com': {
                'content': ['div.caas-body', 'div.article-body', 'div[data-module="ArticleBody"]'],
                'title': ['h1[data-test-locator="headline"]', 'h1', '.headline']
            },
            'automotive-news.com': {
                'content': ['div.article-body', 'div.story-body', 'div.field-name-body'],
                'title': ['h1.headline', 'h1', '.article-title']
            },
            'motor1.com': {
                'content': ['div.article-body', 'div.content-body', 'div.post-content'],
                'title': ['h1.title', 'h1', '.article-title']
            },
            
            # 기본 선택자 (우선순위별)
            'default': {
                'content': ['article', 'div.article-body', 'div.article_body', 'div.content', 'div.post-content', '.article-content', '.news-content', '.story-body', 'main', '[role="main"]'],
                'title': ['h1', '.article-title', '.news-title', '.headline', '.title', 'title']
            }
        }
    
    def extract_content(self, url: str, timeout: int = 15) -> ExtractionResult:
        """
        하이브리드 방식으로 URL에서 기사 본문을 추출합니다.
        1차: newspaper3k -> 2차: 커스텀 파서 -> 3차: 고급 Selenium -> 4차: AI API
        
        Args:
            url (str): 기사 URL (Google News RSS URL 포함)
            timeout (int): 요청 타임아웃 (기본값: 15초)
            
        Returns:
            ExtractionResult: 추출 결과 객체
        """
        start_time = time.time()
        self.stats['total_extractions'] += 1
        
        # URL 유효성 검사
        if not url or not url.startswith(('http://', 'https://')):
            return ExtractionResult(
                url=url, 
                error_message="유효하지 않은 URL",
                extraction_time=time.time() - start_time
            )
        
        # Google News RSS URL 처리
        original_url = url
        if 'news.google.com/rss/articles/' in url or 'news.google.com/read/' in url:
            print(f"   🔗 Google News URL 감지 - 원본 URL 추출 중...")
            actual_url = self._resolve_google_news_url_simple(url, timeout)
            if actual_url and actual_url != url:
                url = actual_url
                print(f"   ✅ 원본 URL 추출 성공: {url}")
            else:
                print(f"   ⚠️ 원본 URL 추출 실패 - 원본 URL로 계속 진행")
        
        domain = urlparse(url).netloc.lower()
        
        # 1차: newspaper3k 시도
        if NEWSPAPER3K_AVAILABLE:
            print(f"   📰 1차 newspaper3k 시도 중...")
            result = self._extract_with_newspaper3k(url, domain, timeout)
            if result.success:
                result.extraction_time = time.time() - start_time
                result.url = original_url  # 원본 URL로 설정
                self._update_stats(ExtractionMethod.NEWSPAPER3K, True)
                self.stats['total_successes'] += 1
                print(f"   ✅ newspaper3k 성공!")
                return result
            else:
                print(f"   ❌ newspaper3k 실패: {result.error_message}")
            self._update_stats(ExtractionMethod.NEWSPAPER3K, False)
        else:
            print(f"   ⚠️ newspaper3k 사용 불가")
        
        # 2차: 커스텀 파서 시도
        print(f"   🔧 2차 커스텀 파서 시도 중...")
        result = self._extract_with_custom_parser(url, domain, timeout)
        if result.success:
            result.extraction_time = time.time() - start_time
            result.url = original_url  # 원본 URL로 설정
            self._update_stats(ExtractionMethod.CUSTOM_PARSER, True)
            self.stats['total_successes'] += 1
            print(f"   ✅ 커스텀 파서 성공!")
            return result
        else:
            print(f"   ❌ 커스텀 파서 실패: {result.error_message}")
        self._update_stats(ExtractionMethod.CUSTOM_PARSER, False)
        
        # 3차: 고급 Selenium 시도 (조선비즈 등 JavaScript 사이트)
        if domain in ['biz.chosun.com']:
            print(f"   🏢 3차 고급 Selenium 시도 중...")
            result = self._extract_with_improved_selenium(url, domain, timeout)
            if result.success:
                result.extraction_time = time.time() - start_time
                result.url = original_url  # 원본 URL로 설정
                self._update_stats(ExtractionMethod.SELENIUM, True)
                self.stats['total_successes'] += 1
                print(f"   ✅ 고급 Selenium 성공!")
                return result
            else:
                print(f"   ❌ 고급 Selenium 실패: {result.error_message}")
            self._update_stats(ExtractionMethod.SELENIUM, False)
        
        # 4차: AI API 시도 (활성화된 경우)
        if self.enable_ai_fallback:
            print(f"   🤖 4차 AI 폴백 시도 중...")
            result = self._extract_with_ai_fallback(url, domain, timeout)
            if result.success:
                result.extraction_time = time.time() - start_time
                result.url = original_url  # 원본 URL로 설정
                self._update_stats(ExtractionMethod.AI_FALLBACK, True)
                self.stats['total_successes'] += 1
                print(f"   ✅ AI 폴백 성공!")
                return result
            else:
                print(f"   ❌ AI 폴백 실패: {result.error_message}")
            self._update_stats(ExtractionMethod.AI_FALLBACK, False)
        else:
            print(f"   ⚠️ AI 폴백이 비활성화되어 있습니다.")
        
        # 모든 방법 실패
        return ExtractionResult(
            url=original_url,  # 원본 Google News URL 유지
            domain=domain,
            error_message="모든 추출 방법 실패",
            extraction_time=time.time() - start_time
        )
    
    def _extract_with_newspaper3k(self, url: str, domain: str, timeout: int) -> ExtractionResult:
        """1차: newspaper3k 라이브러리를 사용한 추출"""
        try:
            article = Article(url)
            article.download()
            article.parse()
            
            # 최소 품질 검증
            if len(article.text) < 100 or not article.title:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.NEWSPAPER3K,
                    error_message="newspaper3k: 추출된 내용이 너무 짧음"
                )
            
            cleaned_content = self._clean_content(article.text)
            
            return ExtractionResult(
                title=article.title.strip(),
                content=cleaned_content,
                url=url,
                domain=domain,
                method=ExtractionMethod.NEWSPAPER3K,
                success=True
            )
            
        except Exception as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.NEWSPAPER3K,
                error_message=f"newspaper3k 오류: {str(e)}"
            )
    
    def _extract_with_selenium(self, url: str, domain: str, timeout: int) -> ExtractionResult:
        """3차: Selenium으로 동적 콘텐츠 추출"""
        if not self.driver:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                error_message="Selenium 드라이버가 초기화되지 않음"
            )
        
        try:
            print("   🌐 Selenium으로 페이지 로딩 중...")
            self.driver.get(url)
            
            # JavaScript 렌더링 대기
            wait = WebDriverWait(self.driver, timeout)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)  # 추가 대기
            
            # 렌더링된 HTML 파싱
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # 제목과 본문 추출
            title = ""
            content = ""
            
            # 도메인별 선택자로 시도
            selectors = self.content_selectors.get(domain, self.content_selectors['default'])
            
            # 제목 추출
            for title_selector in selectors['title']:
                title_elem = soup.select_one(title_selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break
            
            # 본문 추출
            for content_selector in selectors['content']:
                content_elem = soup.select_one(content_selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    break
            
            # 결과 검증
            if not content or len(content.strip()) < 100:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                    error_message="Selenium: 본문 추출 실패 또는 내용 부족"
                )
            
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                title=title, content=self._clean_content(content)
            )
            
        except TimeoutException:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                error_message="Selenium: 페이지 로딩 시간 초과"
            )
        except WebDriverException as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                error_message=f"Selenium 오류: {str(e)}"
            )
        except Exception as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                error_message=f"Selenium 예외 발생: {str(e)}"
            )
    
    def _extract_with_improved_selenium(self, url: str, domain: str, timeout: int) -> ExtractionResult:
        """3차: ImprovedNewsExtractor의 고급 Selenium 추출"""
        print("   🌐 고급 Selenium 모드로 시도...")
        
        # 고급 Chrome 옵션 설정 (ImprovedNewsExtractor 방식)
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Google 관련 에러 방지 (고급 옵션)
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-breakpad')
        options.add_argument('--disable-client-side-phishing-detection')
        options.add_argument('--disable-component-extensions-with-background-pages')
        options.add_argument('--disable-default-apps')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-sync')
        options.add_argument('--force-fieldtrials=*BackgroundTracing/default/')
        options.add_argument('--metrics-recording-only')
        options.add_argument('--no-crash-upload')
        options.add_argument('--no-first-run')
        
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        })
        
        # 조선비즈 전용 다중 셀렉터
        chosun_selectors = {
            'title': [
                'h1.article-header__headline',
                'h1.news_title_text',
                '.article-title h1',
                'h1[class*="title"]',
                '.headline h1',
                '.news-headline',
                'h1'
            ],
            'content': [
                'div.article-body',
                'div.news_text_area', 
                '.article-content',
                '#article_body',
                '.article-text',
                '.news-content',
                '.content-body',
                'div[class*="content"]',
                'div[class*="article"]'
            ]
        }
        
        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # 봇 탐지 우회
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print("   🌐 페이지 로딩 중...")
            driver.get(url)
            
            # 페이지 완전 로딩 대기
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # 추가 대기 (동적 콘텐츠)
            time.sleep(3)
            
            # 스크롤해서 모든 콘텐츠 로딩
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # 제목 추출 (다중 셀렉터)
            title = ""
            for selector in chosun_selectors['title']:
                try:
                    element = soup.select_one(selector)
                    if element:
                        title = element.get_text().strip()
                        if title and len(title) > 10:
                            break
                except Exception:
                    continue
            
            # 본문 추출 (고급 방식)
            content = ""
            for selector in chosun_selectors['content']:
                try:
                    element = soup.select_one(selector)
                    if element:
                        # 불필요한 요소 제거
                        for unwanted in element.find_all(['script', 'style', 'nav', 'header', 'footer', 
                                                         '.ad', '.advertisement', '.related', '.comment',
                                                         '[class*="ad"]', '[id*="ad"]']):
                            unwanted.decompose()
                        
                        # 텍스트 추출 및 정제
                        text = element.get_text(separator='\n', strip=True)
                        
                        # 의미있는 문장만 필터링
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        meaningful_lines = [line for line in lines if len(line) > 20 and not self._is_junk_line(line)]
                        
                        if len(meaningful_lines) >= 3:
                            content = '\n\n'.join(meaningful_lines)
                            break
                            
                except Exception:
                    continue
            
            # 폴백: 전체 페이지에서 본문 추정
            if not content:
                content = self._fallback_content_extraction(soup)
            
            if title and content and len(content) > 200:
                print("   ✅ 고급 Selenium으로 성공적 추출!")
                return ExtractionResult(
                    title=title,
                    content=self._clean_content(content),
                    url=url,
                    domain=domain,
                    method=ExtractionMethod.SELENIUM,
                    success=True
                )
            else:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                    error_message="고급 Selenium: 충분한 내용 추출 실패"
                )
                
        except Exception as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.SELENIUM,
                error_message=f"고급 Selenium 오류: {str(e)}"
            )
        finally:
            if driver:
                driver.quit()
    
    def _extract_with_custom_parser(self, url: str, domain: str, timeout: int) -> ExtractionResult:
        """2차: 커스텀 파서를 사용한 추출"""
        try:
            # HTTP 요청
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            # 인코딩 설정
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            # BeautifulSoup으로 파싱
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 제목 추출
            title = self._extract_title_custom(soup, domain)
            
            # 본문 추출
            content = self._extract_content_custom(soup, domain)
            
            if not content or len(content) < 100:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.CUSTOM_PARSER,
                    error_message="커스텀 파서: 본문 추출 실패 또는 내용 부족"
                )
            
            # 본문 정리
            cleaned_content = self._clean_content(content)
            
            return ExtractionResult(
                title=title,
                content=cleaned_content,
                url=url,
                domain=domain,
                method=ExtractionMethod.CUSTOM_PARSER,
                success=True
            )
            
        except requests.exceptions.Timeout:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.CUSTOM_PARSER,
                error_message="커스텀 파서: 요청 타임아웃"
            )
        except Exception as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.CUSTOM_PARSER,
                error_message=f"커스텀 파서 오류: {str(e)}"
            )
    
    def _extract_with_ai_fallback(self, url: str, domain: str, timeout: int) -> ExtractionResult:
        """3차: AI API를 사용한 추출"""
        try:
            # 먼저 HTML 가져오기
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            # HTML에서 텍스트 추출 (간단한 전처리)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 불필요한 태그 제거
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement']):
                tag.decompose()
            
            # 전체 텍스트 추출 (더 관대한 길이 제한)
            raw_text = soup.get_text()[:8000]  # AI API 토큰 제한 고려하되 더 많이
            
            # 텍스트 길이 체크를 더 관대하게 (50자 이상이면 시도)
            if len(raw_text.strip()) < 50:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.AI_FALLBACK,
                    error_message=f"AI 폴백: 추출된 텍스트가 너무 짧음 ({len(raw_text.strip())}자)"
                )
            
            print(f"   📄 AI 분석용 텍스트: {len(raw_text.strip())}자")
            
            # OpenAI API 호출
            prompt = f"""
            다음은 뉴스 웹페이지의 HTML에서 추출한 텍스트입니다. 
            이 중에서 뉴스 기사의 제목과 본문만 추출해주세요.
            광고, 메뉴, 댓글 등은 제외하고 순수한 기사 내용만 추출해주세요.
            
            응답 형식:
            {{
                "title": "기사 제목",
                "content": "기사 본문"
            }}
            
            웹페이지 텍스트:
            {raw_text}
            """
            
            # OpenAI 클라이언트 확인
            if not self.openai_client:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.AI_FALLBACK,
                    error_message="OpenAI 클라이언트가 초기화되지 않음"
                )
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # 빠르고 저렴한 모델
                messages=[
                    {"role": "system", "content": "당신은 웹페이지에서 뉴스 기사를 추출하는 전문가입니다. JSON 형식으로만 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            # AI 응답 파싱
            ai_response = response.choices[0].message.content.strip()
            
            try:
                parsed_result = json.loads(ai_response)
                title = parsed_result.get('title', '제목 없음')
                content = parsed_result.get('content', '')
                
                if len(content) < 100:
                    return ExtractionResult(
                        url=url, domain=domain, method=ExtractionMethod.AI_FALLBACK,
                        error_message="AI 추출: 내용이 너무 짧음"
                    )
                
                cleaned_content = self._clean_content(content)
                
                return ExtractionResult(
                    title=title,
                    content=cleaned_content,
                    url=url,
                    domain=domain,
                    method=ExtractionMethod.AI_FALLBACK,
                    success=True
                )
                
            except json.JSONDecodeError:
                return ExtractionResult(
                    url=url, domain=domain, method=ExtractionMethod.AI_FALLBACK,
                    error_message="AI 응답 파싱 실패"
                )
                
        except Exception as e:
            return ExtractionResult(
                url=url, domain=domain, method=ExtractionMethod.AI_FALLBACK,
                error_message=f"AI API 오류: {str(e)}"
            )
    
    def _extract_title_custom(self, soup: BeautifulSoup, domain: str) -> str:
        """커스텀 제목 추출"""
        # 도메인별 제목 선택자 시도
        domain_config = self.content_selectors.get(domain, self.content_selectors['default'])
        title_selectors = domain_config.get('title', self.content_selectors['default']['title'])
        
        for selector in title_selectors:
            try:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    if title and len(title) > 5:  # 최소 길이 체크
                        return title
            except Exception:
                continue
        
        return "제목을 찾을 수 없음"
    
    def _extract_content_custom(self, soup: BeautifulSoup, domain: str) -> Optional[str]:
        """커스텀 본문 추출"""
        # 도메인별 본문 선택자 시도
        domain_config = self.content_selectors.get(domain, self.content_selectors['default'])
        content_selectors = domain_config.get('content', self.content_selectors['default']['content'])
        
        for selector in content_selectors:
            try:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    if content and len(content) > 100:  # 최소 길이 체크
                        return content
            except Exception:
                continue
        
        return None
    
    def _clean_content(self, content: str) -> str:
        """본문 정리 (개선된 버전)"""
        if not content:
            return ""
        
        # 불필요한 공백 제거
        content = re.sub(r'\s+', ' ', content)
        
        # 광고성 문구 제거 (확장된 패턴)
        ad_patterns = [
            r'저작권자.*?무단.*?금지',
            r'Copyright.*?All rights reserved',
            r'무단전재.*?재배포.*?금지',
            r'기자.*?@.*?\.com',
            r'▶.*?바로가기',
            r'▲.*?사진',
            r'\[.*?기자\]',
            r'이 기사는.*?제공',
            r'관련기사.*?더보기',
            r'구독.*?알림',
            r'댓글.*?남기기',
            r'공유하기',
            r'프린트.*?스크랩',
            r'좋아요.*?싫어요',
            r'SNS.*?공유',
            r'네이버.*?다음',
            r'페이스북.*?트위터',
            r'카카오.*?라인',
            r'광고.*?AD',
            r'Sponsored.*?Content'
        ]
        
        for pattern in ad_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        # 연속된 공백과 줄바꿈 정리
        content = re.sub(r'\s+', ' ', content).strip()
        content = re.sub(r'\n+', '\n', content)
        
        # 길이 제한 (너무 긴 기사는 앞부분만)
        if len(content) > 3000:
            content = content[:3000] + "..."
        
        return content
    
    def _is_junk_line(self, line):
        """쓸모없는 라인 판별 (ImprovedNewsExtractor에서 가져옴)"""
        junk_patterns = [
            r'^\s*\d+\s*$',  # 숫자만
            r'^\s*[^\w\s]*\s*$',  # 특수문자만
            r'관련\s*기사',
            r'더\s*보기',
            r'이전\s*기사',
            r'다음\s*기사',
            r'^\s*AD\s*$',
            r'광고',
            r'구독',
            r'로그인',
            r'회원가입'
        ]
        
        for pattern in junk_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
    
    def _fallback_content_extraction(self, soup):
        """폴백 본문 추출 (ImprovedNewsExtractor에서 가져옴)"""
        # 가장 긴 텍스트 블록 찾기
        all_divs = soup.find_all(['div', 'article', 'section', 'main'])
        best_content = ""
        
        for div in all_divs:
            text = div.get_text().strip()
            if len(text) > len(best_content) and len(text) > 300:
                # 너무 많은 링크가 있으면 스킵
                links = div.find_all('a')
                if len(links) < len(text) / 100:  # 텍스트 100자당 링크 1개 미만
                    best_content = text
        
        return best_content
    
    def _resolve_google_news_url_simple(self, google_news_url: str, timeout: int = 10) -> Optional[str]:
        """Google News URL에서 실제 기사 URL을 추출 (googlenewsdecoder 사용)"""
        try:
            # 1차: googlenewsdecoder 라이브러리 사용
            if GOOGLE_NEWS_DECODER_AVAILABLE:
                print(f"   📦 googlenewsdecoder 라이브러리 사용 중...")
                try:
                    result = gnewsdecoder(google_news_url, interval=1)
                    if result.get("status") and result.get("decoded_url"):
                        decoded_url = result["decoded_url"]
                        print(f"   ✅ 라이브러리로 디코딩 성공: {decoded_url}")
                        return decoded_url
                    else:
                        print(f"   ⚠️ 라이브러리 디코딩 실패: {result.get('message', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ 라이브러리 오류: {str(e)}")
            
            # 2차: 폴백 - 리다이렉트 따라가기
            print(f"   🌐 리다이렉트 폴백 시도 중...")
            response = self.session.get(
                google_news_url, 
                timeout=timeout,
                allow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
            
            final_url = response.url
            if final_url and 'google.com' not in final_url and final_url != google_news_url:
                print(f"   ✅ 리다이렉트로 원본 URL 발견: {final_url}")
                return final_url
            
            print(f"   ❌ 원본 URL 추출 실패")
            return None
            
        except Exception as e:
            print(f"   ❌ Google News URL 해석 실패: {str(e)}")
            return None
    
    def _update_stats(self, method: ExtractionMethod, success: bool):
        """통계 업데이트"""
        method_key = method.value
        self.stats[method_key]['total'] += 1
        if success:
            self.stats[method_key]['success'] += 1
    
    def get_stats(self) -> Dict:
        """추출 통계 반환"""
        stats_copy = self.stats.copy()
        
        # 성공률 계산
        for method in [ExtractionMethod.NEWSPAPER3K, ExtractionMethod.CUSTOM_PARSER, ExtractionMethod.AI_FALLBACK]:
            method_key = method.value
            total = stats_copy[method_key]['total']
            success = stats_copy[method_key]['success']
            stats_copy[method_key]['success_rate'] = (success / total * 100) if total > 0 else 0
        
        # 전체 성공률
        total_extractions = stats_copy['total_extractions']
        total_successes = stats_copy['total_successes']
        stats_copy['overall_success_rate'] = (total_successes / total_extractions * 100) if total_extractions > 0 else 0
        
        return stats_copy
    
    def extract_multiple_articles(self, urls: List[str], parallel: bool = True, max_workers: int = 5, delay: float = 0.5) -> Dict[str, ExtractionResult]:
        """
        여러 기사의 본문을 일괄 추출합니다 (병렬 처리 지원).
        
        Args:
            urls (List[str]): URL 리스트
            parallel (bool): 병렬 처리 사용 여부 (기본값: True)
            max_workers (int): 최대 동시 스레드 수 (기본값: 5)
            delay (float): 순차 처리 시 요청 간 지연 시간 (기본값: 0.5초)
            
        Returns:
            Dict[str, ExtractionResult]: URL을 키로 하고 추출 결과를 값으로 하는 딕셔너리
        """
        results = {}
        
        if parallel and len(urls) > 1:
            # 병렬 처리
            print(f"병렬 처리로 {len(urls)}개 기사 추출 시작 (최대 {max_workers}개 스레드)")
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 모든 URL에 대해 추출 작업을 병렬로 실행
                future_to_url = {
                    executor.submit(self.extract_content, url): url 
                    for url in urls
                }
                
                # 완료된 작업부터 결과 수집
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        results[url] = result
                        status = "✅" if result.success else "❌"
                        method = result.method.value if result.success else "실패"
                        print(f"{status} {url} - {method}")
                    except Exception as e:
                        results[url] = ExtractionResult(
                            url=url, 
                            error_message=f"병렬 처리 중 오류: {str(e)}"
                        )
                        print(f"❌ {url} - 오류: {str(e)}")
            
            elapsed_time = time.time() - start_time
            success_count = sum(1 for result in results.values() if result.success)
            print(f"병렬 추출 완료: {success_count}/{len(urls)}개 성공, 소요시간 {elapsed_time:.2f}초")
            
        else:
            # 순차 처리
            print(f"순차 처리로 {len(urls)}개 기사 추출 시작")
            start_time = time.time()
        
        for i, url in enumerate(urls, 1):
            print(f"기사 {i}/{len(urls)} 추출 중: {url}")
            
            result = self.extract_content(url)
            results[url] = result
            
            status = "✅" if result.success else "❌"
            method = result.method.value if result.success else "실패"
            print(f"{status} 완료 - {method}")
            
            # 요청 간 지연 (서버 부하 방지)
            if i < len(urls):
                time.sleep(delay)
            
            elapsed_time = time.time() - start_time
            success_count = sum(1 for result in results.values() if result.success)
            print(f"순차 추출 완료: {success_count}/{len(urls)}개 성공, 소요시간 {elapsed_time:.2f}초")
        
        return results


# 하이브리드 웹스크래퍼 별칭 (하위 호환성)
NewsWebScraper = HybridNewsWebScraper


# 사용 예시
if __name__ == "__main__":
    # 하이브리드 스크래퍼 초기화
    scraper = HybridNewsWebScraper(
        # openai_api_key="your-api-key-here",  # AI 폴백 사용 시
        enable_ai_fallback=False  # AI 폴백 비활성화 (API 키 없을 때)
    )
    
    # 테스트 URL (실제 존재하는 URL로 테스트)
    test_urls = [
        "https://www.hankyung.com/economy/article/2024010112345",  # 한국경제 예시
        "https://www.mk.co.kr/news/economy/10891234",  # 매일경제 예시
        "https://www.reuters.com/business/autos-transportation/hyundai-motor-2024-01-01/",  # Reuters 예시
        "https://news.yahoo.com/hyundai-electric-vehicle-2024-123456.html"  # Yahoo 예시
    ]
    
    print("=== 하이브리드 스크래퍼 테스트 ===")
    print(f"newspaper3k 사용 가능: {NEWSPAPER3K_AVAILABLE}")
    print(f"OpenAI API 사용 가능: {OPENAI_AVAILABLE}")
    print(f"AI 폴백 활성화: {scraper.enable_ai_fallback}")
    print()
    
    print("=== 단일 기사 추출 테스트 ===")
    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}] 추출 중: {url}")
        result = scraper.extract_content(url)
        
        if result.success:
            print(f"✅ 성공 - 방법: {result.method.value}")
            print(f"   제목: {result.title}")
            print(f"   본문 (앞 200자): {result.content[:200]}...")
            print(f"   도메인: {result.domain}")
            print(f"   추출 시간: {result.extraction_time:.2f}초")
        else:
            print(f"❌ 실패 - {result.error_message}")
        print("-" * 80)
    
    print("\n=== 병렬 일괄 추출 테스트 ===")
    results = scraper.extract_multiple_articles(test_urls, parallel=True, max_workers=3)
    
    print(f"\n=== 추출 결과 요약 ===")
    success_count = sum(1 for result in results.values() if result.success)
    print(f"전체: {len(results)}개, 성공: {success_count}개, 실패: {len(results) - success_count}개")
    
    # 방법별 통계
    method_stats = {}
    for result in results.values():
        if result.success:
            method = result.method.value
            method_stats[method] = method_stats.get(method, 0) + 1
    
    print("\n방법별 성공 통계:")
    for method, count in method_stats.items():
        print(f"  - {method}: {count}개")
    
    print("\n=== 전체 통계 ===")
    stats = scraper.get_stats()
    for method in ['newspaper3k', 'custom_parser', 'ai_fallback']:
        total = stats[method]['total']
        success = stats[method]['success']
        rate = stats[method]['success_rate']
        print(f"{method}: {success}/{total} ({rate:.1f}%)")
    
    print(f"전체 성공률: {stats['overall_success_rate']:.1f}%")
