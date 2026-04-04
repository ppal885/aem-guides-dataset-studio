import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface ConrefPackConfigProps {
  recipe: {
    topic_count?: number;
    reusable_elements_per_topic?: number;
    conref_density?: number;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function ConrefPackConfig({ recipe, onChange }: ConrefPackConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 50 })}
          min={10}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of topics with reusable elements
        </p>
      </div>

      <div>
        <Label>Reusable Elements per Topic</Label>
        <Input
          type="number"
          value={recipe.reusable_elements_per_topic || 3}
          onChange={(e) => onChange({ ...recipe, reusable_elements_per_topic: parseInt(e.target.value) || 3 })}
          min={1}
          max={10}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of reusable elements in each topic
        </p>
      </div>

      <div>
        <Label>Conref Density: {(recipe.conref_density || 0.3) * 100}%</Label>
        <Input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={recipe.conref_density || 0.3}
          onChange={(e) => onChange({ ...recipe, conref_density: parseFloat(e.target.value) })}
        />
        <p className="text-sm text-gray-500 mt-1">
          Percentage of topics that will have conrefs
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
