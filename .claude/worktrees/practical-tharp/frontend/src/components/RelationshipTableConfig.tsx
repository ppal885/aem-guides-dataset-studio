import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { X } from 'lucide-react';
import { Button } from './ui/button';

interface RelationshipTableConfigProps {
  recipe: {
    topic_count?: number;
    relationship_types?: string[];
    relationship_density?: number;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function RelationshipTableConfig({ recipe, onChange }: RelationshipTableConfigProps) {
  const addRelationshipType = () => {
    const types = recipe.relationship_types || [];
    onChange({
      ...recipe,
      relationship_types: [...types, ''],
    });
  };

  const updateRelationshipType = (index: number, value: string) => {
    const types = [...(recipe.relationship_types || [])];
    types[index] = value;
    onChange({ ...recipe, relationship_types: types });
  };

  const removeRelationshipType = (index: number) => {
    const types = [...(recipe.relationship_types || [])];
    types.splice(index, 1);
    onChange({ ...recipe, relationship_types: types });
  };

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
          Number of topics to generate for relationship table
        </p>
      </div>

      <div>
        <Label>Relationship Types</Label>
        <div className="space-y-2">
          {(recipe.relationship_types || ['next', 'previous', 'related']).map((type, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={type}
                onChange={(e) => updateRelationshipType(index, e.target.value)}
                placeholder="e.g., next, previous, related"
              />
              <Button
                onClick={() => removeRelationshipType(index)}
                variant="ghost"
                size="sm"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={addRelationshipType} variant="outline" size="sm">
            Add Relationship Type
          </Button>
        </div>
      </div>

      <div>
        <Label>Relationship Density: {(recipe.relationship_density || 0.3) * 100}%</Label>
        <Input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={recipe.relationship_density || 0.3}
          onChange={(e) => onChange({ ...recipe, relationship_density: parseFloat(e.target.value) })}
        />
        <p className="text-sm text-gray-500 mt-1">
          Percentage of possible relationships to generate (0.0 to 1.0)
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
