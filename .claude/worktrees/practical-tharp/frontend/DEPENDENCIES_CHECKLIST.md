# Frontend Dependencies Checklist

## ✅ All Required Dependencies

To prevent import errors, ensure all these dependencies are installed:

### Core Dependencies
- ✅ `react` - React library
- ✅ `react-dom` - React DOM renderer
- ✅ `react-router-dom` - Routing
- ✅ `clsx` - Class name utility
- ✅ `tailwind-merge` - Tailwind class merging
- ✅ `lucide-react` - Icons

### Radix UI Components (shadcn/ui)
- ✅ `@radix-ui/react-progress` - Progress bar
- ✅ `@radix-ui/react-switch` - Switch component
- ✅ `@radix-ui/react-dialog` - Dialog/Modal
- ✅ `@radix-ui/react-dropdown-menu` - Dropdown menu
- ✅ `@radix-ui/react-select` - Select dropdown
- ✅ `@radix-ui/react-tabs` - Tabs component
- ✅ `@radix-ui/react-toast` - Toast notifications
- ✅ `@radix-ui/react-tooltip` - Tooltip

### Dev Dependencies
- ✅ `@types/node` - Node.js types
- ✅ `@types/react` - React types
- ✅ `@types/react-dom` - React DOM types
- ✅ `@vitejs/plugin-react` - Vite React plugin
- ✅ `vite` - Build tool
- ✅ `typescript` - TypeScript compiler
- ✅ `tailwindcss` - Tailwind CSS
- ✅ `autoprefixer` - CSS autoprefixer
- ✅ `postcss` - CSS processor

## 🚀 Quick Install

```bash
cd aem-guides-dataset-studio/frontend
npm install
```

## 📝 Adding New UI Components

When adding new shadcn/ui components that use Radix UI:

1. Check which `@radix-ui/*` package is needed
2. Add it to `package.json` dependencies
3. Run `npm install`
4. Update this checklist

## 🔍 Common Radix UI Packages

If you see import errors for Radix UI components, add the corresponding package:

- `@radix-ui/react-accordion` - Accordion
- `@radix-ui/react-alert-dialog` - Alert dialog
- `@radix-ui/react-avatar` - Avatar
- `@radix-ui/react-checkbox` - Checkbox
- `@radix-ui/react-collapsible` - Collapsible
- `@radix-ui/react-context-menu` - Context menu
- `@radix-ui/react-hover-card` - Hover card
- `@radix-ui/react-label` - Label
- `@radix-ui/react-menubar` - Menubar
- `@radix-ui/react-navigation-menu` - Navigation menu
- `@radix-ui/react-popover` - Popover
- `@radix-ui/react-radio-group` - Radio group
- `@radix-ui/react-scroll-area` - Scroll area
- `@radix-ui/react-separator` - Separator
- `@radix-ui/react-slider` - Slider
- `@radix-ui/react-slot` - Slot component
