# 한국어 LLM 설치 가이드

이 문서는 **코딩을 전혀 모르는 사용자**가 LLM/에이전트의 도움을 받아
`hermes-autonomous-agent-system`을 자신의 컴퓨터에 설치하도록 돕는 안내서입니다.

> 핵심 목표: 사용자가 명령어를 이해하지 못해도, LLM이 터미널을 열고
> 안전한 순서로 상태를 확인한 뒤 선택지를 보여주며 설치를 진행하게 합니다.

---

## 1. 먼저 LLM에게 붙여넣을 프롬프트

아래 문장을 ChatGPT, Hermes, Codex, Claude Code 같은 LLM에게 그대로 붙여넣으세요.

```text
나는 코딩을 잘 모르는 일반 사용자입니다.
GitHub 저장소 jhun-kim/hermes-autonomous-agent-system 을 내 컴퓨터에 설치하고 싶습니다.

당신은 내 컴퓨터의 터미널을 열어 설치를 도와주는 설치 도우미 역할을 해주세요.
다음 원칙을 지켜주세요.

1. 먼저 내 운영체제(macOS/Windows/Linux), Python 버전, Git 설치 여부를 확인하세요.
2. 위험한 명령은 실행하기 전에 한국어로 설명하고 확인을 받으세요.
3. 처음에는 반드시 dry-run 또는 help 명령으로 확인만 하세요.
4. 저장소를 받을 위치는 가능하면 ~/Documents/GitHub/hermes-autonomous-agent-system 으로 해주세요.
5. 설치 선택지를 한국어로 보여주고 내가 번호를 고르게 해주세요.
6. 내가 일반 사용자라면 기본 설치를, 개발/수정 목적이면 개발자 설치를 선택하게 해주세요.
7. Hermes Discord gateway 연결은 dry-run 검증이 통과하기 전에는 live 모드로 실행하지 마세요.
8. 설치가 끝나면 어떤 명령으로 정상 설치를 확인했는지 알려주세요.

가능하면 저장소 안의 다음 명령을 사용해 설치 선택지를 보여주세요.
python3 -m hasystem.commands.install_ko --dry-run
```

---

## 2. GitHub에서 받은 뒤 처음 실행할 명령

저장소 폴더에서 아래 명령을 실행하면 한국어 선택지가 나옵니다.
`python3 --version`이 3.10보다 낮으면 `python3.11` 또는 `python3.10`으로 바꿔 실행하세요.

```bash
python3 -m hasystem.commands.install_ko --dry-run
```

이미 패키지를 설치했다면 콘솔 명령도 사용할 수 있습니다.

```bash
hasystem-install-ko --dry-run
```

---

## 3. 설치 선택지

### 선택 1: 일반 사용자 설치

목적: 내 컴퓨터에서 HASYSTEM 명령을 사용할 수 있게 설치합니다.

```bash
python3 -m hasystem.commands.install_ko --choice 1 --dry-run
```

확인 후 실제 실행:

```bash
python3 -m hasystem.commands.install_ko --choice 1 --execute
```

### 선택 2: 개발자 설치

목적: 코드를 수정하거나 테스트를 실행할 수 있는 개발 환경을 만듭니다.

```bash
python3 -m hasystem.commands.install_ko --choice 2 --dry-run
```

확인 후 실제 실행:

```bash
python3 -m hasystem.commands.install_ko --choice 2 --execute
```

### 선택 3: Hermes Discord gateway dry-run 점검

목적: 실제 GitHub issue 생성이나 worker 실행 없이 Discord 이벤트 라우팅만 확인합니다.

```bash
python3 -m hasystem.commands.install_ko --choice 3 --dry-run
```

### 선택 4: LLM에게 설치를 맡기는 흐름 확인

목적: LLM이 터미널에서 어떤 순서로 설치를 안내해야 하는지 확인합니다.

```bash
python3 -m hasystem.commands.install_ko --choice 4 --dry-run
```

---

## 4. 운영체제별 터미널 열기 안내

LLM에게 설치를 맡길 때는 먼저 터미널을 열게 하세요.

- macOS: Spotlight에서 `Terminal` 검색 또는 LLM에게 "Terminal.app을 열어줘"라고 요청
- Windows: 시작 메뉴에서 `Windows Terminal` 또는 `PowerShell` 실행
- Linux: 배포판의 `Terminal` 앱 실행

macOS에서 LLM/에이전트가 직접 터미널을 열 수 있는 환경이라면 다음과 같은 방식으로
저장소 폴더에서 명령을 실행할 수 있습니다.

```bash
open -a Terminal ~/Documents/GitHub/hermes-autonomous-agent-system
```

---

## 5. 안전 체크리스트

설치 전:

- [ ] GitHub 저장소 주소가 `jhun-kim/hermes-autonomous-agent-system`인지 확인
- [ ] Python 3.10 이상인지 확인
- [ ] 처음에는 `--dry-run`으로 명령 목록만 확인
- [ ] `--live`, `--allow-any-repo` 같은 실제 실행/완화 옵션은 의미를 이해한 뒤 사용

설치 후:

- [ ] `hermes-run-loop --help`가 출력되는지 확인
- [ ] `hermes-gateway-adapter --help`가 출력되는지 확인
- [ ] 개발자 설치라면 `python -m pytest -q`가 통과하는지 확인
- [ ] Discord/Hermes 연동은 dry-run 라우팅 확인 후 live 모드로 전환

---

## 6. 문제가 생겼을 때 LLM에게 보여줄 정보

아래 정보를 복사해서 LLM에게 전달하면 문제 해결이 쉬워집니다.

```bash
python3 --version
git --version
pwd
python3 -m hasystem.commands.install_ko --dry-run
```

오류가 난 경우에는 마지막에 실패한 명령과 오류 메시지를 그대로 붙여넣으세요.
