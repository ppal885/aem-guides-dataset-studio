import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface GlossaryPackConfigProps {
  recipe: {
    entry_count?: number;
    include_acronyms?: boolean;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function GlossaryPackConfig({ recipe, onChange }: GlossaryPackConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Entry Count</Label>
        <Input
          type="number"
          value={recipe.entry_count || 100}
          onChange={(e) => onChange({
            type: 'glossary_pack',
            entry_count: parseInt(e.target.value) || 100,
            include_acronyms: recipe.include_acronyms ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={10}
          max={10000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of glossary entries to generate
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-acronyms"
          checked={recipe.include_acronyms !== false}
          onCheckedChange={(checked) => onChange({
            type: 'glossary_pack',
            entry_count: recipe.entry_count ?? 100,
            include_acronyms: checked,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-acronyms">Include Acronyms</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({
            type: 'glossary_pack',
            entry_count: recipe.entry_count ?? 100,
            include_acronyms: recipe.include_acronyms ?? true,
            include_map: checked,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-map">Include Map</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            type: 'glossary_pack',
            entry_count: recipe.entry_count ?? 100,
            include_acronyms: recipe.include_acronyms ?? true,
            include_map: recipe.include_map ?? true,
            pretty_print: checked,
          })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
