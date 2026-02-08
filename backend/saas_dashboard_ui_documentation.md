# SaaS Analytics Dashboard UI Design Assets

## 1. Design System Overview
### Color Palette
- **Base Background**: `#0F172A` (Slate 900)
- **Surface/Card**: `#1E293B` (Slate 800) with `#334155` (Slate 700) border.
- **Primary Accent**: `#38BDF8` (Electric Blue)
- **Data Visualization**:
  - Success: `#4ADE80` (Neon Green)
  - Error: `#F472B6` (Neon Pink)
  - Secondary: `#A78BFA` (Vivid Purple)
- **Glow Effect**: Applied to key buttons and data points for high-contrast visibility.

### Typography (Inter Font)
- **Headings**: Bold (700) or SemiBold (600), letter-spacing: -0.02em.
- **Body**: Regular (400), Slate 400 color for balanced contrast.
- **Numeric Data**: `font-variant-numeric: tabular-nums` for alignment.

## 2. Layout Structure
- **Collapsible Sidebar**: 240px (expanded) to 64px (collapsed). Uses tooltips in collapsed state.
- **Top Navigation Bar**: 64px height, includes breadcrumbs, global search (Cmd+K), and user settings.
- **Main Content Grid**: 12-column Bento UI grid with 24px gap and 32px container padding.

## 3. Component Specifications
- **Interactive Line Chart**: 2px stroke width, neon accents, area fill with gradient, and crosshair interaction.
- **Density Heatmap**: Dark-to-neon color scale, 1px cell spacing, and hover tooltips.
- **Sortable Data Table**: Fixed header, hover highlights (no zebra striping), and right-aligned numeric columns.

## 4. Design Intent
The design focuses on reducing cognitive load through clear visual hierarchy and high-contrast neon accents on a deep slate background. The use of the Inter font ensures maximum readability for complex data sets, while the Bento UI layout provides a modern, organized structure for diverse widgets.
