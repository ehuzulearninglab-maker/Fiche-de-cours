# CV2Portfolio AI

> Transform your CV into a premium portfolio website in seconds, powered by AI.

Upload a PDF resume and instantly receive a beautiful, professional portfolio website with an elegant biography, extracted skills, project showcases, career timeline, and a modern dark UI theme.

## Features

- **AI-Powered CV Analysis** — Extracts name, title, bio, skills, education, experience, projects, languages, certifications, and contact info
- **Professional Content Enhancement** — AI rewrites bios, improves descriptions, and generates compelling summaries
- **Premium Design** — Dark mode, glassmorphism, gradients, smooth Framer Motion animations
- **Auto Theme Generation** — Unique color palette generated based on the user's professional field
- **Public Share Link** — Each portfolio gets a unique URL at `/p/[id]`
- **HTML Download** — Download your complete portfolio as a standalone HTML file
- **Admin Dashboard** — View all generated portfolios, revoke access (protected by token)
- **Responsive** — Looks great on desktop, tablet, and mobile

## Tech Stack

- **Framework**: Next.js 16 (App Router, TypeScript)
- **Styling**: Tailwind CSS 4 + Framer Motion
- **AI**: OpenAI API (GPT-4o-mini)
- **PDF Parsing**: pdf-parse
- **Database**: SQLite via Prisma 7 + better-sqlite3
- **Deployment**: Render.com ready

## Quick Start

### Prerequisites

- Node.js 22+
- An OpenAI API key

### Installation

```bash
git clone https://github.com/ehuzulearninglab-maker/cv2portfolio-ai.git
cd cv2portfolio-ai
npm install
```

### Configuration

Copy the example env file and add your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```
DATABASE_URL="file:./dev.db"
OPENAI_API_KEY="sk-your-openai-api-key"
ADMIN_TOKEN="your-secret-admin-token"
```

### Database Setup

```bash
npx prisma generate
npx prisma migrate dev
```

### Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Pages

| Route | Description |
|---|---|
| `/` | Landing page with features, steps, testimonials |
| `/upload` | Drag & drop CV upload with animated experience |
| `/portfolio/[id]` | Generated portfolio with controls (share, download) |
| `/p/[id]` | Public shareable portfolio page |
| `/admin` | Admin dashboard (requires ADMIN_TOKEN) |

## API Routes

| Method | Route | Description |
|---|---|---|
| POST | `/api/upload` | Upload and parse PDF |
| POST | `/api/generate` | Generate portfolio via AI |
| GET | `/api/download/[id]` | Download portfolio as HTML |
| GET | `/api/portfolios` | List all portfolios (admin) |
| POST | `/api/portfolios/[id]/revoke` | Revoke/restore portfolio (admin) |

## Deploy to Render

1. Push code to GitHub
2. Create a new Web Service on [Render](https://render.com)
3. Connect your GitHub repository
4. Set environment variables:
   - `OPENAI_API_KEY` — Your OpenAI API key
   - `ADMIN_TOKEN` — Secret token for admin access
   - `DATABASE_URL` — `file:./prisma/dev.db`
5. Build command: `npm ci && npx prisma generate && npx prisma migrate deploy && npm run build`
6. Start command: `npm start`

## Project Structure

```
src/
├── app/
│   ├── page.tsx              # Landing page
│   ├── layout.tsx            # Root layout
│   ├── globals.css           # Global styles + animations
│   ├── upload/page.tsx       # Upload page
│   ├── portfolio/[id]/       # Portfolio result page
│   ├── p/[id]/               # Public share page
│   ├── admin/page.tsx        # Admin dashboard
│   └── api/                  # API routes
├── components/
│   └── portfolio/
│       └── PortfolioView.tsx  # Portfolio renderer
└── lib/
    ├── db.ts                 # Prisma client
    ├── openai.ts             # OpenAI integration
    ├── pdf.ts                # PDF text extraction
    └── types.ts              # TypeScript interfaces
prisma/
├── schema.prisma             # Database schema
└── migrations/               # Migration files
```

## Created by

**Michel Affedjou** — Responsable de Projet Innovant — [Ehuzu Learning Lab](https://github.com/ehuzulearninglab-maker)
