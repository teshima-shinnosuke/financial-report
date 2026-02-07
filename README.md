# financial-report

signate competition

## セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/teshima-shinnosuke/financial-report.git
cd financial-report
```

### 2. Python環境の構築

```bash
uv sync
```

### 3. 環境変数の設定

`.env.example` を参考に `.env` ファイルを作成してください。

```bash
cp .env.example .env
# .env を編集して HF_TOKEN を設定
```

## ブランチ運用ルール

```
main        ← 本番用（直接pushしない）
└── develop ← 開発統合用（各自の作業をここにマージ）
     └── feature-igaken （個人作業用）
     └── feature-teshi（個人作業用）
```

### 作業の始め方

```bash
# develop ブランチに移動（最新を取得）
git checkout develop
git pull origin develop

# 作業ブランチを作成
git checkout -b feature/作業内容
```

### 作業中のコミット

```bash
git add .
git commit -m "変更内容を書く"
```

### 作業が終わったらpush

```bash
git push -u origin feature/作業内容
```

push後、GitHub上でPull Requestを作成して `develop` にマージしてください。

### 他の人の変更を取り込みたいとき

```bash
git checkout develop
git pull origin develop
git checkout feature/自分の作業ブランチ
git merge develop
```
