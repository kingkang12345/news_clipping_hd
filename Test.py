import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

def test_openai_connection():
    # .env 파일 로드
    load_dotenv()
    
    # 환경변수 출력으로 설정 확인
    print("=== 환경 변수 설정 확인 ===")
    print(f"API BASE: {os.getenv('OPENAI_API_BASE')}")
    print(f"API KEY: {os.getenv('OPENAI_API_KEY')[:10]}...")  # API 키는 앞부분만 출력
    
    try:
        print("\n=== ChatOpenAI 초기화 및 테스트 ===")
        # ChatOpenAI 초기화
        llm = ChatOpenAI(
            temperature=0,
            #model="gpt-3.5-turbo",
            api_key=os.getenv('OPENAI_API_KEY')
        )
        
        # 간단한 테스트 메시지
        test_message = "안녕하세요. 간단한 테스트입니다. 1+1은 얼마인가요?"
        print(f"테스트 메시지: {test_message}")
        
        # API 호출
        response = llm.invoke([HumanMessage(content=test_message)])
        
        print("\n=== 응답 결과 ===")
        print(f"응답: {response.content}")
        print("\n테스트 성공!")
        return True
        
    except Exception as e:
        print("\n=== 오류 발생 ===")
        print(f"오류 타입: {type(e).__name__}")
        print(f"오류 메시지: {str(e)}")
        return False

if __name__ == "__main__":
    test_openai_connection()
