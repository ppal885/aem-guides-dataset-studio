import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface LegacyPatternsConfigProps {
  recipe: {
    topic_count?: number;
    keydef_count?: number;
    include_map?: boolean;
    pretty_print?: boolean;
    id_prefix?: string;
  };
  onChange: (recipe: any) => void;
  recipeType: 'hub_spoke_inbound' | 'keydef_heavy' | 'map_cyclic';
}

export function LegacyPatternsConfig({ recipe, onChange, recipeType }: LegacyPatternsConfigProps) {
  if (recipeType === 'hub_spoke_inbound') {
    return (
      <div className="space-y-4">
        <div>
          <Label>Topic Count (Spokes)</Label>
          <Input
            type="number"
            value={recipe.topic_count || 100}
            onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 100 })}
            min={10}
            max={1000}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of spoke topics that reference the hub topic
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="include-map"
            checked={recipe.include_map !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_map: checked })}
          />
          <Label htmlFor="include-map">Include Map</Label>
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

  if (recipeType === 'keydef_heavy') {
    return (
      <div className="space-y-4">
        <div>
          <Label>Topic Count</Label>
          <Input
            type="number"
            value={recipe.topic_count || 100}
            onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 100 })}
            min={10}
            max={1000}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of topics to generate
          </p>
        </div>

        <div>
          <Label>Keydef Count</Label>
          <Input
            type="number"
            value={recipe.keydef_count || 50}
            onChange={(e) => onChange({ ...recipe, keydef_count: parseInt(e.target.value) || 50 })}
            min={10}
            max={500}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of key definitions in the map
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="include-map"
            checked={recipe.include_map !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_map: checked })}
          />
          <Label htmlFor="include-map">Include Map</Label>
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

  if (recipeType === 'map_cyclic') {
    return (
      <div className="space-y-4">
        <div>
          <Label>ID Prefix</Label>
          <Input
            type="text"
            value={recipe.id_prefix ?? 't'}
            onChange={(e) => onChange({ ...recipe, id_prefix: e.target.value || 't' })}
            placeholder="t"
          />
          <p className="text-sm text-gray-500 mt-1">
            Unique ID prefix for generated elements
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="pretty-print-map-cyclic"
            checked={recipe.pretty_print !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
          />
          <Label htmlFor="pretty-print-map-cyclic">Pretty Print XML</Label>
        </div>
      </div>
    );
  }

  return null;
}
