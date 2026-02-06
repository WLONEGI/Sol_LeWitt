import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
    try {
        const authHeader = req.headers.get("authorization") || req.headers.get("Authorization");
        if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
            return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
        }

        const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${backendUrl}/api/history`, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader,
            },
            cache: 'no-store'
        });

        if (!response.ok) {
            const detail = await response.text();
            console.error(`History API proxy: Backend error (${backendUrl}): ${response.status} ${detail}`);
            return NextResponse.json({ detail: "Failed to load history" }, { status: response.status });
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
        console.error(`History API proxy error (Target: ${backendUrl}):`, error);
        return NextResponse.json({ detail: "Failed to load history" }, { status: 500 });
    }
}
