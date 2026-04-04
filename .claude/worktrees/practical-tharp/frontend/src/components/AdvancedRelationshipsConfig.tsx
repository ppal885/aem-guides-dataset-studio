import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface AdvancedRelationshipsConfigProps {
  recipe: {
    topic_count?: number;
    relationship_patterns?: string[];
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function AdvancedRelationshipsConfig({ recipe, onChange }: AdvancedRelationshipsConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 100}
          onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 100 })}
          min={10}
          max={10000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of topics with advanced relationship patterns
        </p>
      </div>

      <div>
        <Label>Relationship Patterns</Label>
        <Input
          type="text"
          value={(recipe.relationship_patterns || ['hierarchical', 'cross_map', 'conditional']).join(', ')}
          onChange={(e) => {
            const patterns = e.target.value.split(',').map(p => p.trim()).filter(p => p);
            onChange({ ...recipe, relationship_patterns: patterns });
          }}
          placeholder="hierarchical, cross_map, conditional"
        />
        <p className="text-sm text-gray-500 mt-1">
          Comma-separated list of relationship patterns
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
