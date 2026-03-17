import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface MapParseStressConfigProps {
  recipe: {
    map_count?: number;
    topicrefs_per_map?: number;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function MapParseStressConfig({ recipe, onChange }: MapParseStressConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Map Count</Label>
        <Input
          type="number"
          value={recipe.map_count || 10}
          onChange={(e) => onChange({ ...recipe, map_count: parseInt(e.target.value) || 10 })}
          min={1}
          max={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of maps to generate
        </p>
      </div>

      <div>
        <Label>Topicrefs per Map</Label>
        <Input
          type="number"
          value={recipe.topicrefs_per_map || 1000}
          onChange={(e) => onChange({ ...recipe, topicrefs_per_map: parseInt(e.target.value) || 1000 })}
          min={10}
          max={10000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of topicrefs in each map (1000+ for stress testing)
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
