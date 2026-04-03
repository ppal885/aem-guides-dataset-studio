import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface ReferenceTopicsConfigProps {
  recipe: {
    topic_count?: number;
    properties_per_ref?: number;
    include_choicetable?: boolean;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function ReferenceTopicsConfig({ recipe, onChange }: ReferenceTopicsConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({
            ...recipe,
            type: 'reference_topics',
            topic_count: parseInt(e.target.value) || 50,
          })}
          min={10}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of Reference topics to generate
        </p>
      </div>

      <div>
        <Label>Properties per Reference</Label>
        <Input
          type="number"
          value={recipe.properties_per_ref || 5}
          onChange={(e) => onChange({
            ...recipe,
            type: 'reference_topics',
            properties_per_ref: parseInt(e.target.value) || 5,
          })}
          min={1}
          max={20}
        />
        <p className="text-sm text-gray-500 mt-1">
          Average number of properties in each reference topic
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-choicetable-ref"
          checked={recipe.include_choicetable === true}
          onCheckedChange={(checked) => onChange({
            ...recipe,
            type: 'reference_topics',
            include_choicetable: checked,
          })}
        />
        <Label htmlFor="include-choicetable-ref">Include Option Table</Label>
        <p className="text-xs text-gray-400 ml-1">(adds simpletable to every reference topic)</p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({
            ...recipe,
            type: 'reference_topics',
            include_map: checked,
          })}
        />
        <Label htmlFor="include-map">Include Map</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            ...recipe,
            type: 'reference_topics',
            pretty_print: checked,
          })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
