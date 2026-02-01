import { NextResponse } from 'next/server';

export async function GET() {
    try {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${backendUrl}/api/history`, {
            headers: {
                'Content-Type': 'application/json',
            },
            cache: 'no-store'
        });

        if (!response.ok) {
            console.error(`History API proxy: Backend error (${backendUrl}): ${response.statusText}`);
            return NextResponse.json([], { status: 200 }); // Return empty array instead of 500 to keep UI stable
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
        console.error(`History API proxy error (Target: ${backendUrl}):`, error);
        return NextResponse.json([], { status: 200 }); // Graceful fallback
    }
}
