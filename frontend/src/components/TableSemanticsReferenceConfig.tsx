import { Input } from './ui/input';
import { Label } from './ui/label';

interface TableSemanticsReferenceConfigProps {
  recipe: {
    type: string;
    id_prefix?: string;
    issue_summary?: string;
  };
  onChange: (recipe: TableSemanticsReferenceConfigProps['recipe']) => void;
}

export function TableSemanticsReferenceConfig({ recipe, onChange }: TableSemanticsReferenceConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>ID prefix</Label>
        <Input
          type="text"
          value={recipe.id_prefix ?? 'tblalign'}
          onChange={(e) => onChange({ ...recipe, id_prefix: e.target.value || 'tblalign' })}
          placeholder="tblalign"
        />
        <p className="text-sm text-gray-500 mt-1">Prefix for generated element IDs (must start with a letter or underscore).</p>
      </div>
      <div>
        <Label>Issue summary (optional)</Label>
        <Input
          type="text"
          value={recipe.issue_summary ?? ''}
          onChange={(e) => onChange({ ...recipe, issue_summary: e.target.value })}
          placeholder="Short title for the reference topic"
          maxLength={200}
        />
        <p className="text-sm text-gray-500 mt-1">
          When set, used as the topic title (truncated to 200 characters). Otherwise a default title is used.
        </p>
      </div>
    </div>
  );
}
