import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Folder, File, Search, ChevronRight, ChevronDown, Download, Loader2 } from 'lucide-react';

interface FileNode {
  path: string;
  size?: number;
  compressed_size?: number;
}

interface DirectoryNode {
  path: string;
}

interface DatasetStructure {
  files: FileNode[];
  directories: DirectoryNode[];
}

interface DatasetExplorerProps {
  jobId: string;
  jobName: string;
}

export function DatasetExplorer({ jobId, jobName }: DatasetExplorerProps) {
  const [structure, setStructure] = useState<DatasetStructure | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    loadStructure();
  }, [jobId]);

  const loadStructure = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v1/datasets/${jobId}/structure`);
      if (response.ok) {
        const data = await response.json();
        setStructure(data.structure);
      } else {
        console.error('Failed to load structure:', response.status);
      }
    } catch (error) {
      console.error('Failed to load structure:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleDirectory = (dirPath: string) => {
    const newExpanded = new Set(expandedDirs);
    if (newExpanded.has(dirPath)) {
      newExpanded.delete(dirPath);
    } else {
      newExpanded.add(dirPath);
    }
    setExpandedDirs(newExpanded);
  };

  const loadFile = async (filePath: string) => {
    setSelectedFile(filePath);
    try {
      const response = await fetch(`/api/v1/datasets/${jobId}/file?file_path=${encodeURIComponent(filePath)}`);
      if (response.ok) {
        const content = await response.text();
        setFileContent(content);
      }
    } catch (error) {
      console.error('Failed to load file:', error);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }

    try {
      const response = await fetch(
        `/api/v1/datasets/${jobId}/search?query=${encodeURIComponent(searchQuery)}`
      );
      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.results || []);
      }
    } catch (error) {
      console.error('Search failed:', error);
    }
  };

  const handleDownload = async () => {
    if (downloading) {
      return;
    }

    setDownloading(true);
    
    try {
      // Use setTimeout to allow UI to update before starting download
      await new Promise(resolve => setTimeout(resolve, 50));
      
      const response = await fetch(`/api/v1/datasets/${jobId}/download`);
      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error('Download failed:', response.status, errorText);
        alert(`Failed to download: ${errorText}`);
        return;
      }
      
      // Get the blob from response (handles streaming internally)
      const blob = await response.blob();
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${jobName || jobId}.zip`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      
      // Cleanup after a short delay to ensure download starts
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }, 100);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download dataset. Please try again.');
    } finally {
      // Delay clearing the loading state slightly to show feedback
      setTimeout(() => {
        setDownloading(false);
      }, 500);
    }
  };

  const buildTree = () => {
    if (!structure) return null;

    const tree: Record<string, { files: FileNode[]; dirs: string[] }> = {};

    // Optimize: Process files in batches for large datasets
    const MAX_FILES_TO_PROCESS = 10000;
    const filesToProcess = structure.files.slice(0, MAX_FILES_TO_PROCESS);
    const hasMoreFiles = structure.files.length > MAX_FILES_TO_PROCESS;

    // Organize files by directory
    filesToProcess.forEach(file => {
      const parts = file.path.split('/');
      const dir = parts.slice(0, -1).join('/') || '/';
      const fileName = parts[parts.length - 1];

      if (!tree[dir]) {
        tree[dir] = { files: [], dirs: [] };
      }
      tree[dir].files.push({ ...file, path: fileName });
    });

    // Add directories (limit to prevent UI slowdown)
    const MAX_DIRS_TO_PROCESS = 1000;
    const dirsToProcess = structure.directories.slice(0, MAX_DIRS_TO_PROCESS);
    
    dirsToProcess.forEach(dir => {
      const dirPath = typeof dir === 'string' ? dir : dir.path || '';
      const parts = dirPath.split('/');
      const parentDir = parts.slice(0, -1).join('/') || '/';
      const dirName = parts[parts.length - 1];

      if (!tree[parentDir]) {
        tree[parentDir] = { files: [], dirs: [] };
      }
      if (!tree[parentDir].dirs.includes(dirName)) {
        tree[parentDir].dirs.push(dirName);
      }
    });

    // Store metadata about truncation
    if (hasMoreFiles || structure.directories.length > MAX_DIRS_TO_PROCESS) {
      (tree as any)._truncated = true;
      (tree as any)._totalFiles = structure.files.length;
      (tree as any)._totalDirs = structure.directories.length;
    }

    return tree;
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return 'N/A';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const tree = buildTree();

  if (loading) {
    return <div className="text-center py-4">Loading dataset structure...</div>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* File Tree */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">{jobName}</CardTitle>
            <Button
              onClick={handleDownload}
              disabled={downloading}
              size="sm"
              variant="outline"
              className="flex items-center gap-2"
            >
              {downloading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Downloading...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Download ZIP
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Search */}
          <div className="flex gap-2">
            <Input
              placeholder="Search files..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
            <Button onClick={handleSearch} size="sm">
              <Search className="h-4 w-4" />
            </Button>
          </div>

          {/* Search Results */}
          {searchResults.length > 0 && (
            <div className="border rounded p-2">
              <div className="text-sm font-semibold mb-2">
                Found {searchResults.length} file(s)
              </div>
              {searchResults.map((result, idx) => (
                <div
                  key={idx}
                  className="text-sm cursor-pointer hover:bg-gray-100 p-1 rounded"
                  onClick={() => loadFile(result.file)}
                >
                  {result.file} ({result.match_count} matches)
                </div>
              ))}
            </div>
          )}

          {/* Directory Tree */}
          {tree && (tree as any)._truncated && (
            <div className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800 mb-2">
              Large dataset detected. Showing first {(tree as any)._totalFiles || 0} files and {(tree as any)._totalDirs || 0} directories.
            </div>
          )}
          <div className="space-y-1 text-sm max-h-[600px] overflow-y-auto">
            {tree && Object.entries(tree).filter(([key]) => key !== '_truncated' && key !== '_totalFiles' && key !== '_totalDirs').map(([dir, { files, dirs }]) => (
              <div key={dir}>
                {dir !== '/' && (
                  <div
                    className="flex items-center gap-1 cursor-pointer hover:bg-gray-100 p-1 rounded"
                    onClick={() => toggleDirectory(dir)}
                  >
                    {expandedDirs.has(dir) ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                    <Folder className="h-4 w-4" />
                    <span>{dir}</span>
                  </div>
                )}
                {expandedDirs.has(dir) && (
                  <div className="ml-4 space-y-1">
                    {dirs.map(subDir => (
                      <div
                        key={subDir}
                        className="flex items-center gap-1 cursor-pointer hover:bg-gray-100 p-1 rounded"
                        onClick={() => toggleDirectory(`${dir}/${subDir}`)}
                      >
                        {expandedDirs.has(`${dir}/${subDir}`) ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        <Folder className="h-4 w-4" />
                        <span>{subDir}</span>
                      </div>
                    ))}
                    {files.map(file => (
                      <div
                        key={file.path}
                        className="flex items-center gap-1 cursor-pointer hover:bg-gray-100 p-1 rounded"
                        onClick={() => loadFile(`${dir}/${file.path}`)}
                      >
                        <File className="h-4 w-4" />
                        <span>{file.path}</span>
                        <span className="text-xs text-gray-500 ml-auto">
                          {formatSize(file.size)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* File Viewer */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-lg">
            {selectedFile ? `Viewing: ${selectedFile}` : 'Select a file to view'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {fileContent ? (
            <pre className="bg-gray-50 p-4 rounded overflow-auto max-h-[600px] text-sm">
              {fileContent}
            </pre>
          ) : (
            <div className="text-center text-gray-500 py-8">
              Select a file from the tree to view its contents
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
