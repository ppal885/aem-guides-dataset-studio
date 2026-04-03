import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface PropertiesTableReferenceConfigProps {
  recipe: {
    topic_count?: number;
    rows_per_table?: number;
    include_prophead?: boolean;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: Record<string, unknown>) => void;
}

export function PropertiesTableReferenceConfig({ recipe, onChange }: PropertiesTableReferenceConfigProps) {
  const patch = (updates: Record<string, unknown>) =>
    onChange({
      type: 'properties_table_reference',
      topic_count: recipe.topic_count ?? 30,
      rows_per_table: recipe.rows_per_table ?? 8,
      include_prophead: recipe.include_prophead !== false,
      include_map: recipe.include_map !== false,
      pretty_print: recipe.pretty_print !== false,
      ...updates,
    });

  return (
    <div className="space-y-4">
      <div>
        <Label>Topic count</Label>
        <Input
          type="number"
          value={recipe.topic_count ?? 30}
          onChange={(e) => patch({ topic_count: Math.max(5, parseInt(e.target.value, 10) || 30) })}
          min={5}
          max={5000}
        />
        <p className="mt-1 text-sm text-gray-500">Reference topics, each with one properties table</p>
      </div>

      <div>
        <Label>Rows per properties table</Label>
        <Input
          type="number"
          value={recipe.rows_per_table ?? 8}
          onChange={(e) => patch({ rows_per_table: Math.max(3, Math.min(25, parseInt(e.target.value, 10) || 8)) })}
          min={3}
          max={25}
        />
        <p className="mt-1 text-sm text-gray-500">
          DITA &lt;property&gt; rows (proptype / propvalue / propdesc) per topic
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="prophead"
          checked={recipe.include_prophead !== false}
          onCheckedChange={(checked) => patch({ include_prophead: checked })}
        />
        <Label htmlFor="prophead">Include prophead (Type / Value / Description)</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map-pt"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => patch({ include_map: checked })}
        />
        <Label htmlFor="include-map-pt">Include map (properties_table_reference.ditamap)</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-pt"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => patch({ pretty_print: checked })}
        />
        <Label htmlFor="pretty-pt">Pretty print XML</Label>
      </div>
    </div>
  );
}
