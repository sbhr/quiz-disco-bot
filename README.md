# Discord 早押しクイズBot

Discordのボイスチャンネル上で動作する、読み上げ機能付きの早押しクイズBotです。

## 特徴
*   **自動読み上げ**: gTTSを使用して問題文をボイスチャンネルで自動的に読み上げます。
*   **早押しシステム**: Discordのボタン機能（UI View）を利用し、一番早くボタンを押したユーザーに解答権を与え、音声を即座に停止します。
*   **あいまい判定**: `thefuzz` ライブラリを使用して、1文字程度の打ち間違いや、ひらがな・カタカナの違いを許容する柔軟な正誤判定を行います。
*   **拡張性**: 将来的なデータベース（SQLite）移行や音声認識（Whisper）連携を見据えたモジュール設計を採用しています。

## 必要な環境
*   Python 3.8以上
*   **FFmpeg** (音声再生に必須)

## セットアップ

1. **リポジトリのクローン**
   ```bash
   git clone <repository-url>
   cd quiz-disco-bot
   ```

2. **仮想環境の構築とパッケージのインストール**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windowsの場合は venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **環境変数の設定**
   `.env.template` をコピーして `.env` ファイルを作成し、ご自身のBotトークンを設定してください。
   ```bash
   cp .env.template .env
   ```
   ```env
   # .env の内容
   DISCORD_BOT_TOKEN=あなたのBotトークン
   ```

4. **Discord Botの権限設定（Developer Portal）**
   *   `bot` および `applications.commands` スコープでサーバーに招待してください。
   *   Privileged Gateway Intents の **Message Content Intent** を必ず有効にしてください。

## 起動方法
```bash
python main.py
```

## 遊び方
1. ご自身のサーバーのいずれかのボイスチャンネルに参加します。
2. テキストチャンネルで `/quiz` と入力し、コマンドを実行します。
3. Botがボイスチャンネルに入室し、問題の読み上げを開始します。
4. チャットに表示される「🔴 早押し！」ボタンを最も早く押したユーザーが解答権を得ます。（ボタンを押すと読み上げが即座に停止します）
5. 10秒以内にテキストチャットで解答を送信してください。

## クイズの追加・編集
問題は `data/questions.csv` に保存されています。CSVファイルを編集することで、自由に問題を追加・変更できます。
*列構成: `question` (問題文), `answer` (正解), `explanation` (解説)*
