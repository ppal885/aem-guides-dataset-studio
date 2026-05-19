import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface SyntaxDiagramReferenceConfigProps {
  recipe: {
    topic_count?: number;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function SyntaxDiagramReferenceConfig({ recipe, onChange }: SyntaxDiagramReferenceConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic count</Label>
        <Input
          type="number"
          value={recipe.topic_count ?? 30}
          onChange={(e) =>
            onChange({
              ...recipe,
              type: 'syntax_diagram_reference',
              topic_count: parseInt(e.target.value, 10) || 30,
            })
          }
          min={5}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Reference topics, each with a <code className="text-xs">syntaxdiagram</code> under{' '}
          <code className="text-xs">refsyn</code>
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="syntax-diag-include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) =>
            onChange({
              ...recipe,
              type: 'syntax_diagram_reference',
              include_map: checked,
            })
          }
        />
        <Label htmlFor="syntax-diag-include-map">Include map (syntax_diagram_reference.ditamap)</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="syntax-diag-pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) =>
            onChange({
              ...recipe,
              type: 'syntax_diagram_reference',
              pretty_print: checked,
            })
          }
        />
        <Label htmlFor="syntax-diag-pretty-print">Pretty print XML</Label>
      </div>
    </div>
  );
}
