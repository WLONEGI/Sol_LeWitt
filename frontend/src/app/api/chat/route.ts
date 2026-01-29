
import { NextRequest, NextResponse } from 'next/server';

// export const runtime = 'edge'; // Removed for local dev stability

export async function POST(req: NextRequest) {
    try {
        const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
        const body = await req.json();

        console.log(`[Proxy] Requesting ${backendUrl}/api/chat/stream`);
        const response = await fetch(`${backendUrl}/api/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        console.log(`[Proxy] Response status: ${response.status}`);

        if (!response.ok) {
            return NextResponse.json(
                { error: `Backend error: ${response.statusText}` },
                { status: response.status }
            );
        }

        // Forward the stream directly with Data Stream Protocol headers
        return new Response(response.body, {
            headers: {
                'Content-Type': 'text/plain; charset=utf-8',
                'Cache-Control': 'no-cache, no-transform',
                'Connection': 'keep-alive',
                'X-Vercel-AI-Data-Stream': 'v1',
            },
        });

    } catch (error) {
        console.error('Proxy error:', error);
        return NextResponse.json(
            { error: 'Internal Server Error' },
            { status: 500 }
        );
    }
}
