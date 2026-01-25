import { NextResponse } from 'next/server';

export async function GET() {
    try {
        const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
        const response = await fetch(`${backendUrl}/api/history`, {
            headers: {
                'Content-Type': 'application/json',
            },
            cache: 'no-store'
        });

        if (!response.ok) {
            return NextResponse.json(
                { error: `Backend error: ${response.statusText}` },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error('History API proxy error:', error);
        return NextResponse.json([], { status: 500 });
    }
}
