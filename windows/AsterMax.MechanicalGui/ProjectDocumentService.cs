using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

internal static class ProjectDocumentService
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = false,
        Converters = { new JsonStringEnumConverter() }
    };

    public static async Task SaveAsync(
        AsterMaxProjectDocument document,
        string path,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(document);
        if (string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("A project path is required.", nameof(path));

        Validate(document);
        document.ModifiedUtc = DateTimeOffset.UtcNow;

        var fullPath = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(fullPath);
        if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);

        var temporaryPath = fullPath + ".tmp";
        await using (var stream = new FileStream(
            temporaryPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            64 * 1024,
            FileOptions.Asynchronous | FileOptions.WriteThrough))
        {
            await JsonSerializer.SerializeAsync(stream, document, Options, cancellationToken);
            await stream.FlushAsync(cancellationToken);
        }

        File.Move(temporaryPath, fullPath, true);
    }

    public static async Task<AsterMaxProjectDocument> LoadAsync(
        string path,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("A project path is required.", nameof(path));

        var fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath))
            throw new FileNotFoundException("The AsterMax project does not exist.", fullPath);

        await using var stream = new FileStream(
            fullPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            64 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan);

        var document = await JsonSerializer.DeserializeAsync<AsterMaxProjectDocument>(stream, Options, cancellationToken)
            ?? throw new InvalidDataException("The project file is empty or invalid.");
        Validate(document);
        return document;
    }

    public static void MarkObsolete(AsterMaxProjectDocument document, Guid changedObjectId)
    {
        ArgumentNullException.ThrowIfNull(document);
        var byId = document.Objects.ToDictionary(item => item.Id);
        if (!byId.ContainsKey(changedObjectId))
            throw new InvalidOperationException($"Project object {changedObjectId} was not found.");

        var queue = new Queue<Guid>();
        var visited = new HashSet<Guid>();
        queue.Enqueue(changedObjectId);

        while (queue.Count > 0)
        {
            var id = queue.Dequeue();
            if (!visited.Add(id)) continue;

            if (byId.TryGetValue(id, out var current) && current.State is ProjectObjectState.Solved or ProjectObjectState.UpToDate)
                current.State = ProjectObjectState.Obsolete;

            foreach (var dependent in byId.Values.Where(item => item.DependsOn.Any(reference => reference.Id == id)))
                queue.Enqueue(dependent.Id);
        }
    }

    public static void Validate(AsterMaxProjectDocument document)
    {
        if (document.SchemaVersion != AsterMaxProjectDocument.CurrentSchemaVersion)
            throw new InvalidDataException(
                $"Unsupported project schema {document.SchemaVersion}; expected {AsterMaxProjectDocument.CurrentSchemaVersion}.");

        var objects = document.Objects.ToList();
        var duplicate = objects.GroupBy(item => item.Id).FirstOrDefault(group => group.Count() > 1);
        if (duplicate is not null)
            throw new InvalidDataException($"Project object identifier {duplicate.Key} is duplicated.");

        var ids = objects.Select(item => item.Id).ToHashSet();
        foreach (var item in objects)
        {
            if (string.IsNullOrWhiteSpace(item.Name))
                throw new InvalidDataException($"Project object {item.Id} has no name.");
            foreach (var dependency in item.DependsOn)
                if (!ids.Contains(dependency.Id))
                    throw new InvalidDataException(
                        $"Project object '{item.Name}' depends on missing object {dependency.Id} ({dependency.Kind}).");
        }
    }
}
